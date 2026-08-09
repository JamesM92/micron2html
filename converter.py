"""
Micron markup → HTML converter.

Goal: NomadNet parity — render the same Micron source the way the real
NomadNet client would, not just the way any one third-party client does.
The reference sources are NomadNet's own:
  - Guide.py (the in-app spec, written for page authors):
    https://github.com/markqvist/NomadNet/blob/master/nomadnet/ui/textui/Guide.py
  - MicronParser.py (the reference implementation):
    https://github.com/markqvist/NomadNet/blob/master/nomadnet/ui/textui/MicronParser.py

Where the two disagree (the parser accepts something the guide never
teaches), this converter follows the guide — that's what real page authors
actually write. Where NomadNet supports something this converter can't
fully reproduce (live-refreshing partials, which need JS this pure-Python
library doesn't ship), that's called out at the relevant function rather
than silently ignored — see README's "Known limitations".

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
# Anchors
#
# Ported verbatim from NomadNet's MicronParser.py (slugify_micron / its
# strip regex), so auto-anchor slugs generated here match what real
# NomadNet would generate for the same heading text.
# ---------------------------------------------------------------------------

_MICRON_STRIP_RE = re.compile(
    r"`[FB]T[0-9a-fA-F]{6}"
    r"|`[FB][0-9a-fA-F]{3}"
    r"|`:[A-Za-z0-9_\-]*"
    r"|`[!*_=fbacrl`<>{]"
)

_ANCHOR_NAME_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
)


def slugify_micron(text: Optional[str]) -> str:
    """Slugify heading text into an anchor name, matching NomadNet exactly.

    Strips Micron formatting tokens first (colour, bold/italic/underline/
    reset, alignment, link/field/partial-open, and anchor-declaration
    tokens), then lowercases, collapses runs of non-alphanumeric characters
    into a single hyphen, and strips leading/trailing hyphens.

    ">Hello World" -> "hello-world"
    ">Introduction & Setup" -> "introduction-setup"
    """
    if text is None:
        return ""
    stripped = _MICRON_STRIP_RE.sub("", text)
    return re.sub(r"[^A-Za-z0-9]+", "-", stripped).strip("-").lower()


# ---------------------------------------------------------------------------
# Tables
#
# NomadNet renders `t ... `t blocks as literal box-drawing-character ASCII
# art (via RNS's MarkdownToMicron.format_table_raw), not a semantic HTML
# <table> — that's what real NomadNet clients actually show, so that's what
# this converter builds too, for genuine visual parity.
# ---------------------------------------------------------------------------

_TABLE_TOGGLE_RE = re.compile(r"^`t([lcr]?)(\d*)$")

_TABLE_H, _TABLE_V = "─", "│"
_TABLE_TL, _TABLE_TR, _TABLE_BL, _TABLE_BR = "┌", "┐", "└", "┘"
_TABLE_ML, _TABLE_MR, _TABLE_TM, _TABLE_BM, _TABLE_MM = "├", "┤", "┬", "┴", "┼"

_TABLE_MIN_COL_WIDTH = 3

# Strips colour/bold/italic/underline/reset tokens for width-measurement
# purposes only — a cell's *visible* width shouldn't count its formatting.
_MICRON_TOKEN_RE = re.compile(
    r"`[FB]T[0-9a-fA-F]{6}"
    r"|`[FB][0-9a-fA-F]{3}"
    r"|`[!*_=fb]"
)


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
    anchors: set = field(default_factory=set)          # claimed anchor names, first-wins
    next_heading_map: list = field(default_factory=list)  # line idx -> next heading's slug
    line_index: int = 0           # current line, set by convert()'s loop
    table_mode: bool = False      # inside a `t ... `t block
    table_lines: list = field(default_factory=list)
    table_align: str = ""         # "", "l", "c", "r" — captured at `t open
    table_max_width: int = 100    # captured at `t open


@dataclass
class _InlineState:
    """Per-line inline formatting state."""
    bold: bool = False
    italic: bool = False
    underline: bool = False
    tag_stack: list = field(default_factory=list)  # list of (type_str, open_html, close_html)


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
        doc.next_heading_map = self._compute_next_heading_map(lines)
        parts = []

        for idx, line in enumerate(lines):
            doc.line_index = idx
            result = self._process_line(line, node_hash, base_path, authenticated, doc)
            if result is not None:
                parts.append(result)

        # Flush any unclosed literal block
        if doc.literal and doc.literal_lines:
            content = html.escape("\n".join(doc.literal_lines))
            parts.append(f'<pre class="mu-literal">{content}</pre>')

        # Flush any unclosed table
        if doc.table_mode and doc.table_lines:
            raw_lines, align, max_w = doc.table_lines, doc.table_align, doc.table_max_width
            doc.table_mode, doc.table_lines, doc.table_align, doc.table_max_width = False, [], "", 100
            rendered = self._render_table(raw_lines, align, max_w, node_hash,
                                          base_path, authenticated, doc)
            if rendered is not None:
                parts.append(rendered)

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

        # ---- Inside a `t ... `t table block ----
        # Mutually exclusive with doc.literal by construction (both are only
        # entered from the plain fallthrough path below), so this can safely
        # come first.
        if doc.table_mode:
            if _TABLE_TOGGLE_RE.match(line.rstrip("\r").strip()):
                doc.table_mode = False
                raw_lines, align, max_w = doc.table_lines, doc.table_align, doc.table_max_width
                doc.table_lines, doc.table_align, doc.table_max_width = [], "", 100
                return self._render_table(raw_lines, align, max_w,
                                          node_hash, base_path, authenticated, doc)
            doc.table_lines.append(line)
            return None

        # ---- Inside a multi-line literal block ----
        if doc.literal:
            if line.rstrip() == "`=":
                doc.literal = False
                content = html.escape("\n".join(doc.literal_lines))
                doc.literal_lines = []
                # NomadNet: literal lines inherit the surrounding section
                # depth's indent — MicronParser.py's parse_line() wraps
                # every widget in Padding(left=left_indent(state), ...)
                # whenever depth > 0, literal or not.
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

        # ---- Table start: standalone `t[align][width] line ----
        m = _TABLE_TOGGLE_RE.match(stripped.strip())
        if m:
            align_char, width_str = m.group(1), m.group(2)
            doc.table_mode = True
            doc.table_lines = []
            doc.table_align = align_char
            doc.table_max_width = int(width_str) if width_str else 100
            return None

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
            level, heading_text = self._split_heading(line)
            doc.section = level
            if not heading_text:
                # NomadNet: parse_line() returns None for an empty heading —
                # no row at all, not even blank space. Section depth is
                # still updated above.
                return None
            # Auto-anchor: every heading's slugified text becomes a jump
            # target, claimed before parsing the text itself so a same-slug
            # explicit `:name inside this same heading loses the tie.
            slug = slugify_micron(heading_text)
            claimed = self._claim_anchor(doc, slug)
            inner = self._parse_inline(heading_text, node_hash, base_path,
                                       authenticated, doc)
            # Heading bg extends to the container's left edge for ALL levels
            # (bg starts at 0 regardless of depth). The heading TEXT is
            # tabbed inward via `padding-left` so deeper headings indent
            # while their bg still spans the full row.
            text_indent = (level - 1) * 20
            style_attr = f' style="padding-left:{text_indent}px"' if text_indent else ''
            id_attr = f' id="{html.escape(claimed)}"' if claimed else ''
            # NomadNet: only heading levels 1-3 have a defined style
            # (STYLES_DARK/STYLES_LIGHT in MicronParser.py only define
            # heading1/2/3); level 4+ falls back to plain rendering. We
            # render levels >3 as `.mu-line` so they get plain rendering.
            if level == 1:
                cls = "mu-h1"
            elif level == 2:
                cls = "mu-h2"
            elif level == 3:
                cls = "mu-h3"
            else:
                cls = "mu-line"
            return f'<div class="{cls}"{style_attr}{id_attr}>{inner}</div>'

        # ---- Dividers ----
        # NomadNet: only lines starting with `-` produce dividers.
        # `=-`, `==`, `===` etc. fall through and render as regular text.
        s = line.strip()
        if s and s[0] == "-":
            indent = max(0, doc.section - 1) * 20
            style_attr = f' style="margin-left:{indent}px"' if indent else ''
            # NomadNet's parser only honours a custom divider character when
            # the line is *exactly* "-" + one more character (see
            # MicronParser.py's parse_line: `if len(line) == 2`). Any other
            # length — a bare `-`, or `---`, `-==`, etc. — falls back to the
            # default rule, regardless of what follows the first `-`.
            if len(s) == 2:
                if s[1] == "=":
                    # `-=` — row of `=` characters
                    return f'<hr class="mu-hr mu-hr-double"{style_attr}>'
                # `-~`, `-*`, `-X`, etc. — styled divider; preserve the
                # character so the renderer can repeat it across the row.
                char_content = html.escape(s[1])
                return f'<div class="mu-divider"{style_attr}>{char_content}</div>'
            # `-` alone, or any other length (`--`, `---`, `-==`, …) —
            # default thin solid rule (browser-default <hr>).
            return f'<hr class="mu-hr"{style_attr}>'

        # ---- Empty line ----
        if not line.strip():
            return '<div class="mu-blank"></div>'

        # ---- Regular text line ----
        # NomadNet: `B` only sets the colour state used to style each text
        # part as it's emitted (see make_style() in MicronParser.py) — there's
        # no concept of a leading `B` token filling the whole row. Bg only
        # applies inside the explicit span.
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
                        self._close_innermost(state, "strong", out)
                    else:
                        out.append("<strong>")
                        state.tag_stack.append(("strong", "<strong>", "</strong>"))
                    state.bold = not state.bold
                    i += 1

                # Underline  (`_)
                elif nc == "_":
                    if state.underline:
                        self._close_innermost(state, "underline", out)
                    else:
                        out.append('<span class="mu-ul">')
                        state.tag_stack.append(("underline", '<span class="mu-ul">', "</span>"))
                    state.underline = not state.underline
                    i += 1

                # Italic  (`*)
                elif nc == "*":
                    if state.italic:
                        self._close_innermost(state, "em", out)
                    else:
                        out.append("<em>")
                        state.tag_stack.append(("em", "<em>", "</em>"))
                    state.italic = not state.italic
                    i += 1

                # Foreground color  (`Fxxx or `FTxxxxxx)
                elif nc == "F":
                    i += 1
                    color, i = self._parse_color(text, i, n)
                    if color:
                        open_html = f'<span style="color:{color}">'
                        out.append(open_html)
                        state.tag_stack.append(("fg", open_html, "</span>"))

                # Reset foreground  (`f)
                elif nc == "f":
                    self._close_innermost(state, "fg", out)
                    i += 1

                # Background color  (`Bxxx or `BTxxxxxx)
                elif nc == "B":
                    i += 1
                    color, i = self._parse_color(text, i, n)
                    if color:
                        open_html = f'<span style="background-color:{color}">'
                        out.append(open_html)
                        state.tag_stack.append(("bg", open_html, "</span>"))

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

                # Link  (`[label`URL`field1=v1`field2=v2…] or `[URL])
                # NomadNet: `[label`url`fields] has at most 3 backtick-
                # separated components (fields is itself pipe-separated for
                # multiple values, e.g. `a=1|b=2`). More than 3 components
                # renders nothing at all — MicronParser.py's link handler
                # sets link_url = "" in that case, and its `if len(link_url)
                # != 0:` guard skips emitting anything.
                elif nc == "[":
                    i += 1  # past [
                    end = text.find("]", i)
                    if end != -1:
                        link_inner = text[i:end]
                        parts = link_inner.split("`")
                        if len(parts) == 1:
                            url, lbl, fspec = parts[0], "", ""
                        elif len(parts) == 2:
                            lbl, url, fspec = parts[0], parts[1], ""
                        elif len(parts) == 3:
                            lbl, url, fspec = parts[0], parts[1], parts[2]
                        else:
                            lbl, url, fspec = "", "", ""
                        if url:
                            # `#`-prefixed URLs are page-local anchor jumps,
                            # not resolved through the normal URL resolver:
                            # named (`#name`) or "jump to the next heading
                            # after this point" (bare `#`).
                            if url == "#":
                                href = self._resolve_bare_hash_link(doc)
                            elif url.startswith("#"):
                                href = url
                            else:
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

                # Explicit anchor  (`:name) — zero-width jump target.
                # NomadNet: name chars are A-Za-z0-9_-, terminated by any
                # other character. Shares the same claim/first-wins
                # namespace as heading auto-anchors (_claim_anchor). Emitted
                # as an empty inline <span id=...> at the exact point it
                # appears — HTML fragment navigation resolves against any
                # element with a matching id, not just block containers, so
                # this needs no special-casing for multiple anchors on one
                # line or an anchor alone on an otherwise-empty line.
                elif nc == ":":
                    i += 1
                    start = i
                    while i < n and text[i] in _ANCHOR_NAME_CHARS:
                        i += 1
                    name = text[start:i]
                    claimed = self._claim_anchor(doc, name)
                    if claimed:
                        out.append(f'<span id="{html.escape(claimed)}" class="mu-anchor"></span>')

                # Field  (`<flags|name`default>)
                # NomadNet: a field requires a backtick between `<flags|name`
                # and `default>` — MicronParser.py's field handler does
                # `backtick_pos = line.find('`', field_start)` and gives up
                # entirely if it's not found (`pass  # No '`', invalid field`).
                # We mirror that exactly, including for checkbox/radio
                # shorthand that omits the backtick (`<?|name|value>`,
                # `<^|name|value>`) — real NomadNet renders it as broken text
                # too, not an input.
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
                        # Malformed — eat the `<` silently, matching NomadNet.
                        i += 1

                # Partial  (`{URL`refresh`fields})
                # NomadNet's partials asynchronously load and (optionally)
                # periodically re-fetch a fragment of another page in place —
                # see Guide.py's "Partials" section. That's not something a
                # one-shot markup->HTML conversion can reproduce without
                # adding JS, so this renders a plain clickable link to the
                # target URL instead. The `refresh` and `fields` (pipe-
                # separated, may include `pid=<id>`) components are exposed
                # as data-refresh/data-fields/data-pid attributes so a
                # consuming web app can wire up its own live-refresh
                # behaviour if it wants to — no JS shipped here.
                elif nc == "{":
                    end = text.find("}", i + 1)
                    if end != -1:
                        dyn_inner = text[i + 1:end]
                        dyn_parts = dyn_inner.split("`")
                        dyn_url = dyn_parts[0].strip()
                        href = self._resolve_url(dyn_url, node_hash, base_path)
                        extra = self._render_partial_data_attrs(dyn_parts)
                        out.append(
                            f'<a href="{html.escape(href)}" class="mu-dynamic"{extra}>[live]</a>'
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

        Two forms:

          1. **3 hex chars** — each nibble doubled (f→ff, 8→88, 0→00).
             This is the canonical form and the one MeshChat +
             every mainstream .mu page uses.
          2. **``T`` + 6 hex chars** — a 24-bit exact-color extension
             from NomadNet's reference parser (e.g. ``FTrrggbb``).
             Not portable — MeshChat doesn't render it; pages relying
             on it will look wrong on MeshChat. Supported here for
             feature parity with NomadNet's parser and for authors who
             need exact colors on Micron2HTML-based clients, but
             actively discouraged in documentation.

        NomadNet parity notes:
          - Always consume the next 3 (or ``T`` + 6) chars after F/B
            if available, regardless of whether they're valid hex.
            Both NomadNet's MicronParser.py and MeshChat's
            MicronParser.js do this unconditionally so garbage
            doesn't leak into rendered text.
          - If the chars aren't valid hex, no colour is applied
            (the colour-state holds the invalid string; rendering
            ignores it).

        Returns (css_color_str | None, new_index).
        """
        # T<6hex> exact-color extension — check BEFORE the 3-hex path
        # so a `FTrrggbb` isn't mis-consumed as `T` + garbage.
        if i < n and text[i] == "T" and i + 7 <= n:
            h6 = text[i + 1:i + 7]
            if all(c in _HEX for c in h6):
                return "#" + h6.lower(), i + 7
            # Invalid 6-hex — still consume ``T`` + 6 chars so they
            # don't leak into rendered text.
            return None, i + 7
        if i + 3 <= n:
            h3 = text[i:i + 3]
            if all(c in _HEX for c in h3):
                return "#" + "".join(c * 2 for c in h3).lower(), i + 3
            # Invalid hex — still consume the 3 chars to match NomadNet,
            # but signal "no colour" so the caller doesn't open a span.
            return None, i + 3
        return None, i

    def _parse_header_color(self, value: str) -> Optional[str]:
        """Parse a #!fg=X or #!bg=X page-header color value.

        3-hex only. Guide.py's "Page Foreground and Background Colors"
        section doesn't actually state a length restriction for the header
        value — it just gives a 3-hex example (`#!bg=444`) — and NomadNet's
        colour-rendering helpers technically accept 6-hex strings too. We
        deliberately restrict to 3-hex anyway, for the same reason as the
        inline `Fxxx`/`Bxxx` tags (see `_parse_color`): there's no marker
        distinguishing "3-hex" from "6-hex" the way the inline tags use a
        `T` prefix, so allowing both here just means a mistyped or
        ambiguous value silently changes meaning depending on its length.
        One fixed width, applied consistently everywhere, is safer.

        Returns CSS color string or None.
        """
        v = value.strip()
        if len(v) == 3 and all(c in _HEX for c in v):
            return "#" + "".join(c * 2 for c in v).lower()
        return None

    def _resolve_url(self, url: str, node_hash: str, base_path: str) -> str:
        """Convert a Micron URL to an href via the configured resolver."""
        return self._url_resolver(url, node_hash, base_path)

    def _compute_next_heading_map(self, lines: list) -> list:
        """For each line index, find the nearest heading strictly after it.

        Powers the bare `[label`#] link ("jump to the next heading after
        this point"). Returns a list parallel to `lines`, each entry either
        the anchor slug of the nearest following heading or None.

        Two passes: forward records which line has which heading's slug
        (re-simulating first-wins collision handling locally, matching
        `_claim_anchor`); backward fills each index from what's `upcoming`
        *before* folding in that same line's own slug, so a heading never
        targets itself.
        """
        n = len(lines)
        slug_at = [None] * n
        seen = set()
        for k, raw in enumerate(lines):
            if raw.startswith(">"):
                _, heading_text = self._split_heading(raw)
                if heading_text:
                    slug = slugify_micron(heading_text)
                    if slug and slug not in seen:
                        seen.add(slug)
                        slug_at[k] = slug

        next_map = [None] * n
        upcoming = None
        for k in range(n - 1, -1, -1):
            next_map[k] = upcoming
            if slug_at[k] is not None:
                upcoming = slug_at[k]
        return next_map

    def _resolve_bare_hash_link(self, doc: "_DocState") -> str:
        """Resolve a bare `#` link to the next heading after this point.

        Falls back to a harmless "#" when there's no following heading, or
        no document context at all (e.g. convert_inline(), which never runs
        the multi-line pre-pass so next_heading_map is empty).
        """
        if doc.next_heading_map and doc.line_index < len(doc.next_heading_map):
            slug = doc.next_heading_map[doc.line_index]
            if slug:
                return f"#{slug}"
        return "#"

    def _split_heading(self, line: str) -> tuple:
        """Split a `>`-prefixed line into (level, stripped heading text)."""
        level = 0
        while level < len(line) and line[level] == ">":
            level += 1
        return level, line[level:].strip()

    def _claim_anchor(self, doc: "_DocState", name: str) -> Optional[str]:
        """Claim an anchor name in the document's shared namespace.

        Returns the name if it was successfully claimed (non-empty, not
        already taken), else None. First declared wins — a later duplicate
        (whether another heading's auto-slug or an explicit `:name) is
        silently ignored, matching NomadNet's own anchor-collision rule.
        """
        if not name or name in doc.anchors:
            return None
        doc.anchors.add(name)
        return name

    def _render_partial_data_attrs(self, dyn_parts: list) -> str:
        """Build data-refresh/data-fields/data-pid attributes for a partial.

        `dyn_parts` is the backtick-split `{url`refresh`fields}` content.
        Matches NomadNet's own parse_partial(): refresh is a float, and a
        value < 1 (including 0 or unparseable) disables refresh entirely —
        not just "any positive number". `fields` is pipe-separated; a
        `pid=<id>` entry is also surfaced as its own data-pid attribute,
        mirroring NomadNet's special-casing of that one field.
        """
        attrs = []

        if len(dyn_parts) > 1:
            try:
                refresh = float(dyn_parts[1])
            except ValueError:
                refresh = None
            if refresh is not None and refresh >= 1:
                attrs.append(f' data-refresh="{refresh}"')

        if len(dyn_parts) > 2 and dyn_parts[2]:
            fields = dyn_parts[2]
            attrs.append(f' data-fields="{html.escape(fields)}"')
            for f in fields.split("|"):
                if f.startswith("pid="):
                    attrs.append(f' data-pid="{html.escape(f[len("pid="):])}"')
                    break

        return "".join(attrs)

    def _render_field(self, field_content: str, field_data: str,
                      authenticated: bool = False) -> str:
        """Render a Micron input field.

        Matches the field-parsing logic in NomadNet's own MicronParser.py
        (the `elif c == '<':` branch), which liamcottle/reticulum-meshchat's
        MicronParser.js independently arrives at the same behavior for.

        Formats (the `\\`` is the required separator between flags|name and
        default/label):
          text/password : `<[size][!]|name\\`default>`
          checkbox      : `<?[size]|field_name|value[|*]\\`label>`
          radio         : `<^[size]|field_name|value[|*]\\`label>`

        Note: NomadNet's own Guide.py teaches a slightly different checkbox/
        radio style — leave the field's own label empty (`` `<?|name|value`> ``)
        and write the visible label as plain text after the `>`. Embedding
        the label inside the field (as shown above) is equally valid — the
        parser accepts non-empty `field_data` as the label either way — it's
        just not the style the guide's own examples use.

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

            if field_flags and field_flags.isdigit():
                field_width = min(int(field_flags), 256)

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

    def _close_innermost(self, state: _InlineState, tag_type: str, out: list) -> None:
        """Close the named tag, wherever it sits in the stack.

        HTML closing tags are positional/LIFO, so closing something that
        isn't currently innermost can't just emit its close tag in place —
        that would close whatever *is* innermost instead. Unwind: close
        every entry above the target (innermost-first), close the target
        itself, then reopen the unwound entries (in their original order)
        as fresh elements and push them back. Same colour/bold/etc. either
        side, just split across an extra pair of tags at the unwind point.
        """
        for j in range(len(state.tag_stack) - 1, -1, -1):
            if state.tag_stack[j][0] == tag_type:
                above = state.tag_stack[j + 1:]
                for _, _, close_html in reversed(above):
                    out.append(close_html)
                out.append(state.tag_stack[j][2])
                del state.tag_stack[j:]
                for entry in above:
                    out.append(entry[1])
                    state.tag_stack.append(entry)
                return

    def _close_all(self, state: _InlineState) -> list:
        tags = [close for _, _, close in reversed(state.tag_stack)]
        state.tag_stack.clear()
        state.bold = state.italic = state.underline = False
        return tags

    # ------------------------------------------------------------------
    # Table rendering
    # ------------------------------------------------------------------

    def _render_table(self, raw_lines: list, align: str, max_width: int,
                      node_hash: str, base_path: str, authenticated: bool,
                      doc: _DocState) -> Optional[str]:
        """Render a buffered `t ... `t block as box-drawing ASCII art.

        Ports NomadNet's own MarkdownToMicron.format_table_raw() algorithm
        (from RNS's rngit util) so cell content, column widths, and
        alignment match what real NomadNet would draw for the same
        markdown-table input. Generated rows are fed back through
        `_process_line`, so cell content like a colour token renders
        correctly and a table nested under a section picks up its indent
        for free — same as any other text line.
        """
        if len(raw_lines) < 2:
            return None

        header_cells = self._parse_table_row(raw_lines[0])
        ncols = len(header_cells)
        aligns = self._parse_table_alignments(self._parse_table_row(raw_lines[1]), ncols)

        data_rows = []
        for raw in raw_lines[2:]:
            cells = self._parse_table_row(raw)
            cells = (cells + [""] * ncols)[:ncols]
            data_rows.append(cells)

        col_widths = [_TABLE_MIN_COL_WIDTH] * ncols
        for row in [header_cells] + data_rows:
            for j, cell in enumerate(row):
                col_widths[j] = max(col_widths[j], self._visible_width(cell))
        col_widths = self._shrink_table_widths(col_widths, max_width)

        lines = [self._table_border(col_widths, "top"),
                 self._table_row(header_cells, col_widths, ["left"] * ncols),
                 self._table_border(col_widths, "mid")]
        for row in data_rows:
            lines.append(self._table_row(row, col_widths, aligns))
        lines.append(self._table_border(col_widths, "bottom"))

        # Wrap the whole table in the requested alignment via a direct
        # state assignment (not an injected `c/`a pseudo-line) — a bare
        # alignment-only line produces no visible output of its own, which
        # would just add stray empty rows above/below the table.
        if align:
            doc.align = {"l": "left", "c": "center", "r": "right"}[align]

        rendered = []
        for raw in lines:
            out = self._process_line(raw, node_hash, base_path, authenticated, doc)
            if out is not None:
                rendered.append(out)

        if align:
            doc.align = ""
        return f'<div class="mu-table">{"".join(rendered)}</div>'

    def _parse_table_row(self, line: str) -> list:
        """Split a markdown-table row into cells on unescaped `|`."""
        line = line.strip()
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|"):
            line = line[:-1]

        cells = []
        current = []
        escaped = False
        for ch in line:
            if escaped:
                current.append(ch)
                escaped = False
            elif ch == "\\":
                current.append(ch)
                escaped = True
            elif ch == "|":
                cells.append("".join(current).strip())
                current = []
            else:
                current.append(ch)
        cells.append("".join(current).strip())
        return cells

    def _parse_table_alignments(self, cells: list, ncols: int) -> list:
        """Parse a markdown separator row (`:---:`/`--:`/`---`) per column."""
        aligns = []
        for cell in cells:
            c = cell.strip()
            if c.startswith(":") and c.endswith(":"):
                aligns.append("center")
            elif c.endswith(":"):
                aligns.append("right")
            else:
                aligns.append("left")
        aligns += ["left"] * (ncols - len(aligns))
        return aligns[:ncols]

    def _visible_width(self, text: str) -> int:
        """Character width of a cell, ignoring Micron formatting tokens.

        NomadNet's own implementation also consults `wcwidth` for
        double-width glyphs; deliberately not ported here (would add a
        runtime dependency this pure-Python library has never had) —
        documented simplification in the README.
        """
        return len(_MICRON_TOKEN_RE.sub("", text))

    def _pad_cell(self, text: str, width: int, align: str) -> str:
        """Pad (or, if needed, truncate) a cell to `width` visible columns."""
        visible = self._visible_width(text)
        if visible > width:
            # Truncating mid-token could leave an unclosed span/strong tag —
            # dropping formatting on truncation is strictly safer than that.
            text = _MICRON_TOKEN_RE.sub("", text)[:width]
            visible = len(text)
        pad = width - visible
        if align == "right":
            return " " * pad + text
        if align == "center":
            left = pad // 2
            return " " * left + text + " " * (pad - left)
        return text + " " * pad

    def _shrink_table_widths(self, col_widths: list, max_width: int) -> list:
        """Greedily shrink the widest column until the table fits max_width.

        Faithful-effort port of NomadNet's "proportionally shrink the
        widest columns" — not a byte-for-byte match of its exact formula,
        which isn't fully specified in the reference source.
        """
        widths = list(col_widths)
        ncols = len(widths)
        total = sum(widths) + ncols * 3 + 1
        while total > max_width and max(widths) > _TABLE_MIN_COL_WIDTH:
            j = widths.index(max(widths))
            widths[j] -= 1
            total -= 1
        return widths

    def _table_border(self, col_widths: list, kind: str) -> str:
        left, mid, right = {
            "top": (_TABLE_TL, _TABLE_TM, _TABLE_TR),
            "mid": (_TABLE_ML, _TABLE_MM, _TABLE_MR),
            "bottom": (_TABLE_BL, _TABLE_BM, _TABLE_BR),
        }[kind]
        return left + mid.join(_TABLE_H * (w + 2) for w in col_widths) + right

    def _table_row(self, cells: list, col_widths: list, aligns: list) -> str:
        padded = [self._pad_cell(c, w, a) for c, w, a in zip(cells, col_widths, aligns)]
        return _TABLE_V + " " + f" {_TABLE_V} ".join(padded) + " " + _TABLE_V
