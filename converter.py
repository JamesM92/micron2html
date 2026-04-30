"""
Micron markup → HTML converter.

Implements the full Micron specification as documented in:
  https://github.com/markqvist/NomadNet/blob/master/nomadnet/ui/textui/Guide.py

Default page colours match NomadNet's terminal defaults:
  background  #000000  (black)
  foreground  #aaaaaa  (light grey)
"""

import html
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

_TAG_RE = re.compile(r'<[^>]+>')

_HEX = frozenset("0123456789abcdefABCDEF")

# Type alias for a URL resolver: (raw_url, node_hash, base_path) -> href
UrlResolver = Callable[[str, str, str], str]


def default_url_resolver(url: str, node_hash: str, base_path: str) -> str:
    """Library default: produce canonical NomadNet URLs without app-specific wrapping.

    - http(s):// URLs pass through unchanged
    - hash:/... and nomadnetwork:// URLs are returned canonicalized as hash://<hash>/<path>
    - relative paths are resolved against (node_hash, base_path)
    - /file/ links are blocked (return "#")
    - empty/unknown returns "#"

    Wrap this in your own resolver to produce app-specific hrefs (e.g. "/page?url=…").
    """
    if not url:
        return "#"

    if url.startswith("http://") or url.startswith("https://"):
        return url

    def _is_blocked(u: str) -> bool:
        return "/file/" in u

    if url.startswith("nomadnetwork://"):
        body = url[len("nomadnetwork://"):]
        return "#" if _is_blocked("/" + body) else f"hash://{body}"

    if url.startswith("hash://"):
        return "#" if _is_blocked(url) else url

    if url.startswith("hash:/"):
        return "#" if _is_blocked(url) else f"hash://{url[len('hash:/'):]}"

    # Bare-hash format: <hex>:/path  or  :/path (current node)
    colon_slash = url.find(":/")
    if colon_slash == 0 and node_hash:
        path_part = url[1:]
        return "#" if _is_blocked(path_part) else f"hash://{node_hash}{path_part}"
    if colon_slash > 0:
        candidate = url[:colon_slash]
        if 8 <= len(candidate) <= 64 and all(c in _HEX for c in candidate):
            full = f"hash://{candidate}{url[colon_slash + 1:]}"
            return "#" if _is_blocked(full) else full

    if url.startswith("/") and node_hash:
        return "#" if _is_blocked(url) else f"hash://{node_hash}{url}"

    if node_hash and url:
        base_dir = (base_path.rsplit("/", 1)[0] + "/") if "/" in base_path else "/"
        return f"hash://{node_hash}{base_dir}{url}"

    return "#"


# ---------------------------------------------------------------------------
# State dataclasses
# ---------------------------------------------------------------------------

@dataclass
class _DocState:
    """Document-level state that persists across lines."""
    align: str = ""              # "", "left", "center", "right"
    section: int = 0             # current section depth (number of leading >)
    literal: bool = False        # inside a `= ... `= block
    literal_lines: list = field(default_factory=list)
    doc_fg: str = ""             # CSS color from #!fg= header
    doc_bg: str = ""             # CSS color from #!bg= header


@dataclass
class _InlineState:
    """Per-line inline formatting state."""
    bold: bool = False
    italic: bool = False
    underline: bool = False
    literal: bool = False
    tag_stack: list = field(default_factory=list)  # list of (type_str, close_html)


# ---------------------------------------------------------------------------
# Converter
# ---------------------------------------------------------------------------

class MicronConverter:
    """Convert Micron markup text to an HTML fragment.

    Parameters
    ----------
    url_resolver
        Callable ``(raw_url, node_hash, base_path) -> href`` invoked for every
        link in the input. Defaults to :func:`default_url_resolver`, which
        emits canonical ``hash://...`` URLs. Web frontends typically wrap
        that with their own URL pattern (e.g. ``/page?url=…``).
    """

    def __init__(self, url_resolver: Optional[UrlResolver] = None):
        self._url_resolver: UrlResolver = url_resolver or default_url_resolver

    def convert(self, text: str, node_hash: str = "", base_path: str = "",
                authenticated: bool = False) -> str:
        """Convert a full Micron document to an HTML fragment.

        Parameters
        ----------
        text
            Micron source text.
        node_hash
            Destination hash of the source NomadNet node — used to resolve
            relative and node-relative links.
        base_path
            Path of the current page (e.g. ``/page/index.mu``) — used to
            resolve relative links against the page's directory.
        authenticated
            When ``True``, form fields are rendered as editable ``<input>``
            elements. When ``False`` (default), they are rendered as
            disabled inputs so guests can see them but not submit.
        """
        lines = text.split("\n")
        doc = _DocState()
        parts = []

        for line in lines:
            result = self._process_line(line, node_hash, base_path, authenticated, doc)
            if result is not None:
                parts.append(result)

        # Flush any unclosed literal block
        if doc.literal and doc.literal_lines:
            content = html.escape("\n".join(doc.literal_lines))
            parts.append(f'<pre class="mu-literal">{content}</pre>')

        body = "\n".join(parts)

        # Wrap with page-level colours if #!fg/#!bg headers were found
        styles = []
        if doc.doc_bg:
            styles.append(f"background-color:{doc.doc_bg}")
        if doc.doc_fg:
            styles.append(f"color:{doc.doc_fg}")
        if styles:
            return f'<div class="mu-page" style="{";".join(styles)}">{body}</div>'
        return body

    def convert_inline(self, text: str, node_hash: str = "", base_path: str = "",
                       authenticated: bool = False) -> str:
        """Convert a single line of Micron markup to inline HTML.

        Returns formatted HTML *without* the ``<div class="mu-line">`` wrapper —
        useful for rendering titles, message previews, brand elements, and
        anywhere you need just the inline formatting (colors, bold, links).

        Multi-line input has all newlines replaced with spaces.
        """
        single = text.replace("\n", " ").strip()
        return self._parse_inline(single, node_hash, base_path, authenticated, _DocState())

    def to_text(self, text: str) -> str:
        """Render Micron markup to plain text, stripping formatting and colors.

        Useful for message previews in conversation lists, search indexing,
        accessibility tools, and CLI/terminal display where HTML is unwanted.
        Links retain only their label text; URLs are dropped. Literal blocks
        appear as their raw content. Page-level fg/bg headers are dropped.
        """
        html_out = self.convert(text)
        plain = _TAG_RE.sub("", html_out)
        return html.unescape(plain).strip()

    # ------------------------------------------------------------------
    # Line-level processing
    # ------------------------------------------------------------------

    def _process_line(self, line: str, node_hash: str, base_path: str,
                      authenticated: bool, doc: _DocState) -> Optional[str]:

        # ---- Inside a multi-line literal block ----
        if doc.literal:
            if line.rstrip() == "`=":
                doc.literal = False
                content = html.escape("\n".join(doc.literal_lines))
                doc.literal_lines = []
                return f'<pre class="mu-literal">{content}</pre>'
            doc.literal_lines.append(line)
            return None

        # ---- Comment / page-header lines (start with #) ----
        if line.startswith("#"):
            raw = line.strip()
            if raw.startswith("#!bg="):
                color = self._parse_header_color(raw[5:].strip())
                if color:
                    doc.doc_bg = color
            elif raw.startswith("#!fg="):
                color = self._parse_header_color(raw[5:].strip())
                if color:
                    doc.doc_fg = color
            return None

        stripped = line.rstrip("\r")

        # ---- Literal block start/end: standalone `= line ----
        if stripped.strip() == "`=":
            doc.literal = True
            doc.literal_lines = []
            return None

        # ---- Full reset: standalone `` resets doc-level state ----
        if stripped.strip() == "``":
            doc.align = ""
            return None

        # ---- Section headings: line starts with one or more > ----
        if line.startswith(">"):
            level = 0
            while level < len(line) and line[level] == ">":
                level += 1
            doc.section = level
            heading_text = line[level:].strip()
            if not heading_text:
                return None  # unnamed section — just changes indentation
            inner = self._parse_inline(heading_text, node_hash, base_path,
                                       authenticated, doc)
            indent = (level - 1) * 20
            style = f'padding-left:{indent}px' if indent else ''
            style_attr = f' style="{style}"' if style else ''
            cls = "mu-h1" if level == 1 else "mu-h2" if level == 2 else "mu-h3"
            return f'<div class="{cls}"{style_attr}>{inner}</div>'

        # ---- Dividers ----
        s = line.strip()
        if s and all(c == "-" for c in s) and len(s) >= 1:
            indent = doc.section * 20
            style = f' style="margin-left:{indent}px"' if indent else ''
            return f'<hr class="mu-hr"{style}>'
        if s.startswith("-=") or s.startswith("=-"):
            return '<hr class="mu-hr mu-hr-double">'
        # Styled divider: -<char(s)>
        if s.startswith("-") and len(s) > 1 and s[1] not in ("-", "="):
            char_content = html.escape(s[1:])
            indent = doc.section * 20
            style_attr = f' style="padding-left:{indent}px"' if indent else ''
            return f'<div class="mu-divider"{style_attr}>{char_content}</div>'

        # ---- Empty line ----
        if not line.strip():
            return '<div class="mu-blank"></div>'

        # ---- Regular text line ----
        line_bg = self._extract_line_bg_color(line)
        inner = self._parse_inline(line, node_hash, base_path, authenticated, doc)

        style_parts = []
        if line_bg:
            style_parts.append(f"background-color:{line_bg}")
        if doc.align:
            style_parts.append(f"text-align:{doc.align}")
        indent = doc.section * 20
        if indent:
            style_parts.append(f"padding-left:{indent}px")

        style_attr = f' style="{";".join(style_parts)}"' if style_parts else ''
        return f'<div class="mu-line"{style_attr}>{inner}</div>'

    # ------------------------------------------------------------------
    # Inline parsing  (character-level state machine)
    # ------------------------------------------------------------------

    def _parse_inline(self, text: str, node_hash: str, base_path: str,
                      authenticated: bool, doc: _DocState) -> str:
        state = _InlineState()
        out = []
        i = 0
        n = len(text)

        while i < n:
            ch = text[i]

            # ---- Inline literal mode: pass through until closing `= ----
            if state.literal:
                if ch == "`" and i + 1 < n and text[i + 1] == "=":
                    state.literal = False
                    i += 2
                else:
                    out.append(html.escape(ch))
                    i += 1
                continue

            # ---- Backslash escape ----
            if ch == "\\" and i + 1 < n:
                out.append(html.escape(text[i + 1]))
                i += 2
                continue

            # ---- Backtick token ----
            if ch == "`":
                i += 1
                if i >= n:
                    out.extend(self._close_all(state))
                    break
                nc = text[i]

                # Reset ALL formatting  (``)
                if nc == "`":
                    out.extend(self._close_all(state))
                    doc.align = ""
                    i += 1

                # Bold  (`!)
                elif nc == "!":
                    if state.bold:
                        out.append("</strong>")
                        self._pop_tag(state, "strong")
                    else:
                        out.append("<strong>")
                        state.tag_stack.append(("strong", "</strong>"))
                    state.bold = not state.bold
                    i += 1

                # Underline  (`_)
                elif nc == "_":
                    if state.underline:
                        out.append("</span>")
                        self._pop_tag(state, "underline")
                    else:
                        out.append('<span class="mu-ul">')
                        state.tag_stack.append(("underline", "</span>"))
                    state.underline = not state.underline
                    i += 1

                # Italic  (`*)
                elif nc == "*":
                    if state.italic:
                        out.append("</em>")
                        self._pop_tag(state, "em")
                    else:
                        out.append("<em>")
                        state.tag_stack.append(("em", "</em>"))
                    state.italic = not state.italic
                    i += 1

                # Foreground color  (`Fxxx or `FTxxxxxx)
                elif nc == "F":
                    i += 1
                    color, i = self._parse_color(text, i, n)
                    if color:
                        out.append(f'<span style="color:{color}">')
                        state.tag_stack.append(("fg", "</span>"))

                # Reset foreground  (`f)
                elif nc == "f":
                    self._close_innermost(state, "fg", out)
                    i += 1

                # Background color  (`Bxxx or `BTxxxxxx)
                elif nc == "B":
                    i += 1
                    color, i = self._parse_color(text, i, n)
                    if color:
                        out.append(f'<span style="background-color:{color}">')
                        state.tag_stack.append(("bg", "</span>"))

                # Reset background  (`b)
                elif nc == "b":
                    self._close_innermost(state, "bg", out)
                    i += 1

                # Alignment — updates persistent doc state
                elif nc == "c":
                    doc.align = "center"
                    i += 1
                elif nc == "l":
                    doc.align = "left"
                    i += 1
                elif nc == "r":
                    doc.align = "right"
                    i += 1
                elif nc == "a":
                    doc.align = ""
                    i += 1

                # Inline literal mode  (`=)
                elif nc == "=":
                    state.literal = True
                    i += 1

                # Link  (`[label`URL`fieldspec] or `[URL])
                elif nc == "[":
                    i += 1  # past [
                    end = text.find("]", i)
                    if end != -1:
                        link_inner = text[i:end]
                        parts = link_inner.split("`")
                        if len(parts) >= 2:
                            lbl, url = parts[0], parts[1]
                            fspec = parts[2] if len(parts) > 2 else ""
                        else:
                            url = parts[0]
                            lbl = ""
                            fspec = ""
                        href = self._resolve_url(url, node_hash, base_path)
                        display = html.escape(lbl) if lbl else html.escape(url)
                        extra = (f' data-field-spec="{html.escape(fspec)}"'
                                 if fspec else "")
                        out.append(
                            f'<a href="{html.escape(href)}" class="mu-link"{extra}>'
                            f'{display}</a>'
                        )
                        i = end + 1
                    else:
                        out.append("[")

                # Field  (`<...>)
                elif nc == "<":
                    i += 1  # past <
                    end = text.find(">", i)
                    if end != -1:
                        out.append(self._render_field(text[i:end], authenticated))
                        i = end + 1
                    else:
                        out.append("<")

                # Dynamic include  (`{URL`refresh})
                elif nc == "{":
                    end = text.find("}", i + 1)
                    if end != -1:
                        dyn_inner = text[i + 1:end]
                        dyn_url = dyn_inner.split("`")[0].strip()
                        href = self._resolve_url(dyn_url, node_hash, base_path)
                        out.append(
                            f'<a href="{html.escape(href)}" class="mu-dynamic">[live]</a>'
                        )
                        i = end + 1
                    else:
                        out.append("`{")
                        i += 1

                else:
                    # Unknown token — emit literal backtick; reprocess nc next iteration
                    out.append("`")

                continue

            out.append(html.escape(ch))
            i += 1

        out.extend(self._close_all(state))
        return "".join(out)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_color(self, text: str, i: int, n: int):
        """Parse a Micron color token after the F/B prefix.

        Formats
          T + 6 hex chars  — 24-bit true color
          3 hex chars      — each nibble doubled  (f→ff, 8→88, 0→00)

        Returns (css_color_str | None, new_index).
        """
        if i >= n:
            return None, i
        if text[i] == "T":
            j = i + 1
            if j + 6 <= n:
                h6 = text[j:j + 6]
                if all(c in _HEX for c in h6):
                    return f"#{h6.lower()}", j + 6
            return None, i
        if i + 3 <= n:
            h3 = text[i:i + 3]
            if all(c in _HEX for c in h3):
                return "#" + "".join(c * 2 for c in h3).lower(), i + 3
        return None, i

    def _parse_header_color(self, value: str) -> Optional[str]:
        """Parse a #!fg=X or #!bg=X color value.  Returns CSS color or None."""
        v = value.strip()
        if len(v) == 3 and all(c in _HEX for c in v):
            return "#" + "".join(c * 2 for c in v).lower()
        if len(v) == 6 and all(c in _HEX for c in v):
            return f"#{v.lower()}"
        return None

    def _extract_line_bg_color(self, line: str) -> Optional[str]:
        """Scan the start of a raw Micron line for a background-colour token.

        Skips leading alignment / bold / italic / underline / fg-colour tokens.
        Returns a CSS color string or None.  Used to apply the colour to the
        wrapper <div> so it fills the full line width (terminal behaviour).
        """
        i, n = 0, len(line)
        while i + 1 < n and line[i] == "`":
            nc = line[i + 1]
            if nc in ("c", "l", "r", "a", "!", "*", "_"):
                i += 2
            elif nc in ("F", "B"):
                is_bg = (nc == "B")
                i += 2
                if i < n and line[i] == "T":
                    j = i + 1
                    hs = line[j:j + 6] if j + 6 <= n else ""
                    if len(hs) == 6 and all(c in _HEX for c in hs):
                        color = f"#{hs.lower()}"
                        i = j + 6
                    else:
                        return None
                else:
                    hs = line[i:i + 3] if i + 3 <= n else ""
                    if len(hs) == 3 and all(c in _HEX for c in hs):
                        color = "#" + "".join(c * 2 for c in hs).lower()
                        i += 3
                    else:
                        return None
                if is_bg:
                    return color
                # foreground colour — skip and keep scanning
            else:
                break
        return None

    def _resolve_url(self, url: str, node_hash: str, base_path: str) -> str:
        """Convert a Micron URL to an href via the configured resolver."""
        return self._url_resolver(url, node_hash, base_path)

    def _render_field(self, inner: str, authenticated: bool = False) -> str:
        """Render a Micron input field.

        Formats
          text/password : [size][!]|name`default   or   name`default
          checkbox      : ?|field_name|value[|*]
          radio         : ^|field_name|value[|*]
        """
        dis = "" if authenticated else " disabled"
        cls = ' class="mu-field"'

        # Split on | to detect field type
        pipe = inner.split("|")
        flags_raw = pipe[0]
        flags = "".join(c for c in flags_raw if not c.isdigit())

        # ---- Checkbox  (`<?|name|value[|*]>) ----
        if "?" in flags:
            name  = html.escape(pipe[1].strip()) if len(pipe) > 1 else ""
            value = html.escape(pipe[2].strip()) if len(pipe) > 2 else "on"
            pre   = len(pipe) > 3 and pipe[3].strip() == "*"
            chk   = " checked" if pre else ""
            return f'<input type="checkbox" name="{name}" value="{value}"{dis}{chk}>'

        # ---- Radio  (`<^|name|value[|*]>) ----
        if "^" in flags:
            name  = html.escape(pipe[1].strip()) if len(pipe) > 1 else ""
            value = html.escape(pipe[2].strip()) if len(pipe) > 2 else ""
            pre   = len(pipe) > 3 and pipe[3].strip() == "*"
            chk   = " checked" if pre else ""
            return f'<input type="radio" name="{name}" value="{value}"{dis}{chk}>'

        # ---- Text / password ----
        # Format: [size][!]|name`default  OR  name`default  (no pipe)
        if "|" in inner:
            size_flags = pipe[0]
            rest = "|".join(pipe[1:])
        else:
            size_flags = ""
            rest = inner

        tick = rest.split("`", 1)
        name    = html.escape(tick[0]) if tick else ""
        default = html.escape(tick[1]) if len(tick) > 1 else ""

        size_digits = "".join(c for c in size_flags if c.isdigit())
        is_pass     = "!" in size_flags

        size_attr  = f' size="{size_digits}"' if size_digits else ""
        itype      = "password" if is_pass else "text"

        return (f'<input type="{itype}" name="{name}" value="{default}"'
                f'{size_attr}{dis}{cls}>')

    def _pop_tag(self, state: _InlineState, tag_type: str) -> None:
        for j in range(len(state.tag_stack) - 1, -1, -1):
            if state.tag_stack[j][0] == tag_type:
                state.tag_stack.pop(j)
                return

    def _close_innermost(self, state: _InlineState, tag_type: str, out: list) -> None:
        for j in range(len(state.tag_stack) - 1, -1, -1):
            if state.tag_stack[j][0] == tag_type:
                out.append(state.tag_stack[j][1])
                state.tag_stack.pop(j)
                return

    def _close_all(self, state: _InlineState) -> list:
        tags = [close for _, close in reversed(state.tag_stack)]
        state.tag_stack.clear()
        state.bold = state.italic = state.underline = False
        state.literal = False
        return tags
