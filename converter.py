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

# ---------------------------------------------------------------------------
# Braille rendering
#
# The bundled Roboto Mono Nerd Font has no Braille glyphs at all, and the
# system-monospace fallbacks on most platforms render Braille at much less
# than full cell width — adjacent cells leave visible gaps and a row of
# full-dot Braille reads as separated dots instead of a contiguous grid.
#
# We post-process the converted HTML to replace each Braille character
# (U+2800–U+28FF) with a `<span class="mu-braille">` whose dots are
# painted by CSS via `--mu-braille-dots` (a list of `radial-gradient`s,
# one per raised dot). The result is font-independent: the cells always
# render at exactly `1ch` wide with the dots at fixed fractional positions.
#
# The bundled `micron-meshchat.css` ships the matching `.mu-braille` rule.
# ---------------------------------------------------------------------------

_BRAILLE_DOT_POSITIONS = (
    # (left%, top%) for each bit, in order: dot1 dot2 dot3 dot4 dot5 dot6 dot7 dot8.
    # 8-dot Braille fits in a 2×4 grid.
    #
    # Vertical: pushed close to cell edges (5/35/65/95) so the inter-cell gap
    # between cell N's bottom dot at y=95% and cell N+1's top dot at y=5% is
    # small (10% of cell height vs 30% intra-cell) — adjacent rows of Braille
    # flow tightly together instead of separating into discrete rows by a
    # visible horizontal stripe.
    #
    # Horizontal: insetted from cell edges (27/73) so dots are slightly
    # closer together within a cell (46% spacing) than between cells (54%).
    # The 8% asymmetry produces a faintly perceptible character-cell
    # boundary, useful for distinguishing one Braille glyph from the next
    # in dense content without obvious gaps that would break the grid feel.
    (27, 5), (27, 35), (27, 65),
    (73, 5), (73, 35), (73, 65),
    (27, 95), (73, 95),
)

_BRAILLE_RE = re.compile(r"<[^>]*>|[⠀-⣿]")


def _braillify_html(html_str: str) -> str:
    """Replace Braille codepoints in HTML text with CSS-drawn span elements.

    Tags and attribute values are matched first (greedy alternation) and
    pass through untouched, so nothing inside ``<a href="…">`` or
    ``data-…`` attributes gets rewritten.
    """
    def repl(m: "re.Match[str]") -> str:
        s = m.group(0)
        if s.startswith("<"):
            return s
        bits = ord(s) - 0x2800
        grads = []
        for i in range(8):
            if bits & (1 << i):
                x, y = _BRAILLE_DOT_POSITIONS[i]
                grads.append(
                    f"radial-gradient(circle at {x}% {y}%, "
                    f"currentColor 0.07em, transparent 0.08em)"
                )
        style = f' style="--mu-braille-dots:{",".join(grads)}"' if grads else ""
        return f'<span class="mu-braille"{style}></span>'
    return _BRAILLE_RE.sub(repl, html_str)

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
                authenticated: bool = False, render_braille: bool = True) -> str:
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
        render_braille
            When ``True`` (default), Braille characters (U+2800–U+28FF) in
            the output are replaced with ``<span class="mu-braille">``
            elements that render the dots via CSS — see the comment above
            ``_braillify_html`` for rationale. Pass ``False`` to keep the
            raw Braille codepoints (e.g. when feeding the result to a
            downstream consumer that strips tags).
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
            result = f'<div class="mu-page" style="{";".join(styles)}">{body}</div>'
        else:
            result = body
        return _braillify_html(result) if render_braille else result

    def convert_inline(self, text: str, node_hash: str = "", base_path: str = "",
                       authenticated: bool = False, render_braille: bool = True) -> str:
        """Convert a single line of Micron markup to inline HTML.

        Returns formatted HTML *without* the ``<div class="mu-line">`` wrapper —
        useful for rendering titles, message previews, brand elements, and
        anywhere you need just the inline formatting (colors, bold, links).

        Multi-line input has all newlines replaced with spaces.

        ``render_braille`` controls the Braille post-processing — see
        :meth:`convert` for details.
        """
        single = text.replace("\n", " ").strip()
        result = self._parse_inline(single, node_hash, base_path, authenticated, _DocState())
        return _braillify_html(result) if render_braille else result

    def to_text(self, text: str) -> str:
        """Render Micron markup to plain text, stripping formatting and colors.

        Useful for message previews in conversation lists, search indexing,
        accessibility tools, and CLI/terminal display where HTML is unwanted.
        Links retain only their label text; URLs are dropped. Literal blocks
        appear as their raw content. Page-level fg/bg headers are dropped.
        """
        html_out = self.convert(text, render_braille=False)
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
                # MeshChat parity: literal lines inherit the surrounding
                # section depth's indent (its parser applies section indent
                # to every line, literal or not).
                indent = max(0, doc.section - 1) * 20
                style_attr = f' style="margin-left:{indent}px"' if indent else ''
                return f'<pre class="mu-literal"{style_attr}>{content}</pre>'
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
                # MeshChat parity: empty heading line still emits a blank row
                # (its parseLine returns null and the outer convertMicronToHtml
                # loop appends a <br>). State (section depth) is updated above.
                return '<div class="mu-blank"></div>'
            inner = self._parse_inline(heading_text, node_hash, base_path,
                                       authenticated, doc)
            # Heading bg extends to the container's left edge for ALL levels
            # (bg starts at 0 regardless of depth). The heading TEXT is
            # tabbed inward via `padding-left` so deeper headings indent
            # while their bg still spans the full row.
            text_indent = (level - 1) * 20
            style_attr = f' style="padding-left:{text_indent}px"' if text_indent else ''
            # MeshChat parity: only heading levels 1–3 have a bg block; level
            # 4+ falls back to the "plain" style (no bg, default fg). We
            # render levels >3 as `.mu-line` so they get plain rendering.
            if level == 1:
                cls = "mu-h1"
            elif level == 2:
                cls = "mu-h2"
            elif level == 3:
                cls = "mu-h3"
            else:
                cls = "mu-line"
            return f'<div class="{cls}"{style_attr}>{inner}</div>'

        # ---- Dividers ----
        # MeshChat parity: only lines starting with `-` produce dividers.
        # `=-`, `==`, `===` etc. fall through and render as regular text.
        s = line.strip()
        if s and s[0] == "-":
            indent = max(0, doc.section - 1) * 20
            style_attr = f' style="margin-left:{indent}px"' if indent else ''
            if len(s) == 1:
                # `-` alone — thin solid rule (browser-default <hr>)
                return f'<hr class="mu-hr"{style_attr}>'
            if s[1] == "=":
                # `-=` — row of `=` characters
                return f'<hr class="mu-hr mu-hr-double"{style_attr}>'
            # `--`, `-~`, `-*`, `-X`, etc. — styled divider; preserve the
            # character so the renderer can repeat it across the row.
            char_content = html.escape(s[1])
            return f'<div class="mu-divider"{style_attr}>{char_content}</div>'

        # ---- Empty line ----
        if not line.strip():
            return '<div class="mu-blank"></div>'

        # ---- Regular text line ----
        # MeshChat parity: no line-level bg from a leading `B` token (its
        # parser doesn't do that). Bg only applies inside the explicit span.
        inner = self._parse_inline(line, node_hash, base_path, authenticated, doc)

        style_parts = []
        if doc.align:
            style_parts.append(f"text-align:{doc.align}")
        indent = max(0, doc.section - 1) * 20
        if indent:
            style_parts.append(f"margin-left:{indent}px")

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

                # Link  (`[label`URL`field1=v1`field2=v2…] or `[URL])
                elif nc == "[":
                    i += 1  # past [
                    end = text.find("]", i)
                    if end != -1:
                        link_inner = text[i:end]
                        parts = link_inner.split("`")
                        if len(parts) >= 2:
                            lbl, url = parts[0], parts[1]
                            # Preserve all backtick-separated field specs.
                            # Earlier versions only took parts[2], silently
                            # dropping every field after the first.
                            fspec = "`".join(parts[2:]) if len(parts) > 2 else ""
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

                # Field  (`<flags|name`default>)
                # MeshChat parity: a field requires a backtick between
                # `<flags|name` and `default>`. Without it, MeshChat's
                # parseField returns null and the `<` is silently eaten.
                # We mirror that exactly so checkbox/radio shorthand that
                # omits the backtick (`<?|name|value>`, `<^|name|value>`)
                # produces the same broken render in both renderers.
                elif nc == "<":
                    field_start = i + 1
                    backtick_pos = text.find("`", field_start)
                    end = text.find(">", backtick_pos + 1) if backtick_pos != -1 else -1
                    if backtick_pos != -1 and end != -1:
                        field_content = text[field_start:backtick_pos]
                        field_data = text[backtick_pos + 1:end]
                        out.append(self._render_field(field_content, field_data, authenticated))
                        i = end + 1
                    else:
                        # Malformed — eat the `<` silently, matching MeshChat.
                        i += 1

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
                    # Unknown token — silently consume both the backtick and
                    # the unknown char, matching the behaviour of NomadNet's
                    # MicronParser (and Liam Cottle's MicronParser.js port).
                    # If you want a literal backtick, use `\`` to escape it.
                    i += 1

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

        Format: 3 hex chars — each nibble doubled (f→ff, 8→88, 0→00).

        MeshChat parity:
          - Always consume the next 3 chars after F/B (if available),
            regardless of whether they're valid hex. This matches NomadNet's
            MicronParser and Liam Cottle's MicronParser.js, both of which
            do `line.substr(i+1,3)` + `skip = 3` unconditionally.
          - If the 3 chars aren't valid hex, no colour is applied (the
            colour-state holds the invalid string; rendering ignores it),
            but the 3 chars are still consumed so they don't leak as text.
          - The 24-bit `T<6hex>` extension that Micron2HTML used to accept
            has been dropped — neither MeshChat nor NomadNet support it.

        Returns (css_color_str | None, new_index).
        """
        if i + 3 <= n:
            h3 = text[i:i + 3]
            if all(c in _HEX for c in h3):
                return "#" + "".join(c * 2 for c in h3).lower(), i + 3
            # Invalid hex — still consume the 3 chars to match MeshChat,
            # but signal "no colour" so the caller doesn't open a span.
            return None, i + 3
        return None, i

    def _parse_header_color(self, value: str) -> Optional[str]:
        """Parse a #!fg=X or #!bg=X color value.  Returns CSS color or None."""
        v = value.strip()
        if len(v) == 3 and all(c in _HEX for c in v):
            return "#" + "".join(c * 2 for c in v).lower()
        if len(v) == 6 and all(c in _HEX for c in v):
            return f"#{v.lower()}"
        return None

    def _resolve_url(self, url: str, node_hash: str, base_path: str) -> str:
        """Convert a Micron URL to an href via the configured resolver."""
        return self._url_resolver(url, node_hash, base_path)

    def _render_field(self, field_content: str, field_data: str,
                      authenticated: bool = False) -> str:
        """Render a Micron input field.

        Mirrors `parseField()` in liamcottle/reticulum-meshchat MicronParser.js.

        Formats (the `\\`` is the required separator between flags|name and
        default/label):
          text/password : `<[size][!]|name\\`default>`
          checkbox      : `<?[size]|field_name|value[|*]\\`label>`
          radio         : `<^[size]|field_name|value[|*]\\`label>`

        `field_content` is everything between `<` and the backtick.
        `field_data` is everything between the backtick and `>`.
        """
        dis = "" if authenticated else " disabled"

        field_masked = False
        field_width = 24
        field_type = "field"
        field_name = field_content
        field_value = ""
        field_prechecked = False

        if "|" in field_content:
            f_components = field_content.split("|")
            field_flags = f_components[0]
            field_name = f_components[1] if len(f_components) > 1 else ""

            if "^" in field_flags:
                field_type = "radio"
                field_flags = field_flags.replace("^", "")
            elif "?" in field_flags:
                field_type = "checkbox"
                field_flags = field_flags.replace("?", "")
            elif "!" in field_flags:
                field_masked = True
                field_flags = field_flags.replace("!", "")

            if field_flags:
                try:
                    w = int(field_flags)
                    field_width = min(w, 256)
                except ValueError:
                    pass

            if len(f_components) > 2:
                field_value = f_components[2]
            if len(f_components) > 3 and f_components[3] == "*":
                field_prechecked = True

        name_attr = html.escape(field_name)
        if field_type in ("checkbox", "radio"):
            value = field_value or field_data
            label = field_data
            chk = " checked" if field_prechecked else ""
            return (f'<input type="{field_type}" name="{name_attr}" '
                    f'value="{html.escape(value)}"{dis}{chk}> '
                    f'{html.escape(label)}')

        # Text / password
        itype = "password" if field_masked else "text"
        return (f'<input type="{itype}" name="{name_attr}" '
                f'value="{html.escape(field_data)}" '
                f'size="{field_width}"{dis} class="mu-field">')

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
