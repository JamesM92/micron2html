# Micron2HTML

[![CI](https://github.com/JamesM92/Micron2HTML/actions/workflows/ci.yml/badge.svg)](https://github.com/JamesM92/Micron2HTML/actions/workflows/ci.yml)
[![Security](https://github.com/JamesM92/Micron2HTML/actions/workflows/security.yml/badge.svg)](https://github.com/JamesM92/Micron2HTML/actions/workflows/security.yml)
[![PyPI version](https://img.shields.io/pypi/v/micron2html.svg)](https://pypi.org/project/micron2html/)
[![Python versions](https://img.shields.io/pypi/pyversions/micron2html.svg)](https://pypi.org/project/micron2html/)

A Python library and CLI tool that converts [Micron](https://github.com/markqvist/NomadNet) markup to HTML.

Micron is the terminal markup language used by [NomadNet](https://github.com/markqvist/NomadNet) nodes. This library lets you render Micron pages in web browsers and other HTML-capable environments.

**Design goal: NomadNet parity.** The converter aims to render the same Micron source the way the real NomadNet client would — following [NomadNet's own Guide](https://github.com/markqvist/NomadNet/blob/master/nomadnet/ui/textui/Guide.py) (the in-app spec written for page authors) and [MicronParser.py](https://github.com/markqvist/NomadNet/blob/master/nomadnet/ui/textui/MicronParser.py) (the reference implementation), not any one third-party client's behavior. Where those two disagree with each other, this library follows the Guide, since that's what real page authors read and write to. See [Known limitations](#known-limitations) for syntax NomadNet supports that isn't implemented here yet.

## Installation

```bash
pip install Micron2HTML
```

Or from source:

```bash
git clone https://github.com/JamesM92/Micron2HTML.git
cd Micron2HTML
pip install -e .
```

No runtime dependencies — pure Python 3.10+.

## Library usage

```python
from micron2html import MicronConverter

conv = MicronConverter()

html = conv.convert(micron_text)

# With context for resolving internal links
html = conv.convert(
    micron_text,
    node_hash="a1b2c3d4...",    # destination hash of the source node
    base_path="/page/index.mu", # current page path
    authenticated=True,         # render form fields as interactive inputs
)

# Inline-only — for titles, message previews, brand strings.
# Returns formatted HTML without the <div class="mu-line"> wrapper.
title_html = conv.convert_inline("`F4af`!My Node`!`f")

# Plain text — strips all formatting and colours, no HTML at all.
text = conv.to_text(micron_text)
```

`convert()` returns an HTML fragment (no `<html>` or `<body>` wrapper). Wrap it in your own template or use the CLI for standalone pages.

### Custom URL resolution

By default, links resolve to canonical `hash://<hash>/<path>` URLs (and `http(s)://` URLs pass through). If your web app uses a different URL pattern — e.g. `/page?url=…` — pass a resolver callback:

```python
import urllib.parse
from micron2html import MicronConverter, default_url_resolver

def my_resolver(url: str, node_hash: str, base_path: str) -> str:
    canonical = default_url_resolver(url, node_hash, base_path)
    if canonical.startswith("hash://"):
        return f"/page?url={urllib.parse.quote(canonical, safe='')}"
    return canonical

conv = MicronConverter(url_resolver=my_resolver)
```

### Default stylesheet

A dark-terminal stylesheet ships with the package — visually styled after [Reticulum MeshChat](https://github.com/liamcottle/reticulum-meshchat)'s NomadNet renderer (its filename reflects that), independent of the markup-parsing parity goal above:

```html
<link rel="stylesheet" href="/static/micron-meshchat.css">
```

The file lives at `micron2html/micron-meshchat.css` in the installed package — copy it into your static directory, or import it via your build pipeline. All rules are scoped to `.mu-*` classes so they won't bleed into the rest of your page.

## CLI usage

```bash
# Convert a file and print to stdout
micron-convert page.mu

# Convert and write to a file
micron-convert page.mu -o page.html

# Read from stdin
cat page.mu | micron-convert -

# Output an HTML fragment instead of a full page
micron-convert page.mu --fragment

# Set the node hash so internal links resolve correctly
micron-convert page.mu --node-hash a1b2c3d4e5f6...

# Strip all formatting and print plain text instead of HTML
micron-convert page.mu --format text
```

## Micron syntax

### Comments and headers

```
# This is a comment — the whole line is stripped from output

#!bg=2a2   Set page background colour (3-hex shorthand: each digit doubled)
#!fg=aaa   Set page foreground colour
```

Deliberately 3-hex-only, matching the inline `` `Fxxx ``/`` `Bxxx `` tags below — NomadNet's own docs would technically permit a 6-hex value here too, but without a marker distinguishing the two (the way the inline tags would need a `T` prefix), a value's meaning would silently depend on its length. One fixed width, applied consistently, is safer.

### Headings and sections

```
>Section heading      h1
>>Subsection          h2
>>>Sub-subsection     h3
```

### Dividers

```
-       Horizontal rule (default style)
-=      Row of `=` characters
-x      Styled divider — repeats character `x` (e.g. -* renders a * row)
```

A custom divider character only takes effect when the line is *exactly* two characters — `-` followed by one more. Any other length, including `---` or `-==`, falls back to the default rule rather than repeating what follows the first `-` (this matches NomadNet's own parser, which only reads a custom divider char off a length-2 line).

### Inline formatting

```
`!text`!      Bold
`*text`*      Italic
`_text`_      Underline

`Fxxx         Set foreground colour (3-hex shorthand: each digit doubled — `FF40 → #ff4400)
`f            Reset foreground colour to default

`Bxxx         Set background colour (3-hex shorthand)
`b            Reset background colour to default

``            Reset ALL inline formatting (bold, italic, underline, colours, alignment)
```

### Alignment

```
`a            Left align (default)
`c            Centre align
`r            Right align
```

### Links

```
`[Label`href]                        Labelled link
`[`http://example.com]               URL-only link
`[Label`/relative/path.mu]           Relative path (resolved against base_path)
`[Label`hash://a1b2c3/page.mu]       Node link (resolved against node_hash)
```

Links can also submit form-field data to a node-side page: `` `[Label`url`fields] ``, where `fields` is a single pipe-separated segment — `*` (submit every field on the page), field names to include (`username|auth_token`), or literal `key=value` pairs, mixable in any order (`*|action=preview|id=42`). The parsed spec is emitted verbatim as `data-field-spec` for the consuming application to read. A link with more than 3 backtick-separated components (e.g. `` `[Label`url`a=1`b=2] ``, extra fields separated by backticks instead of pipes) renders nothing at all, matching NomadNet exactly — always use pipes for multiple fields.

### Anchors

```
`:name                                Declare an anchor at this point (zero-width, renders nothing)
`[Label`#name]                        Jump to a named anchor on this page
`[Label`#]                            Jump to the next `>` heading after this link's position
```

Every heading also becomes an anchor automatically, named by slugifying its text: lowercase, runs of non-alphanumeric characters collapsed to a single hyphen, leading/trailing hyphens stripped. `` >Hello World `` → anchor `hello-world`; `` >Introduction & Setup `` → `introduction-setup`. Explicit `` `:name `` anchors and heading auto-anchors share one namespace per page — if a name collides, the first one declared wins.

Named-anchor links (`` `[Label`#name] ``) resolve to a plain `href="#name"` and work regardless of document order, since HTML's own fragment navigation resolves against whatever element ends up with that `id`. The bare `` `[Label`#] `` form is different: it looks forward from its own position in the document for the nearest following heading and links to that — useful for "Continue ↓" buttons without naming every section. `slugify_micron()` (also exported from the package) is available standalone if you want to build your own table of contents from a Micron document.

Cross-page anchors (linking to a named anchor on a *different* page) use NomadNet's own `anchor=name` request-field convention rather than a URL fragment, and are out of scope here — a single `convert()` call over one page's text has no way to know another page's heading layout.

### Partials

```
`{URL}                                Partial with no auto-refresh
`{URL`refresh}                        Partial that re-fetches every `refresh` seconds (0 or omitted disables it)
`{URL`refresh`field1|field2|pid=x}    Partial with request fields; `pid=` targets a specific partial for refresh
```

In real NomadNet, a partial asynchronously loads a fragment of another page and (optionally) re-fetches it in place on an interval — see NomadNet's Guide, "Partials" section. That's not something a one-shot markup→HTML conversion can reproduce without adding JavaScript, so Micron2HTML renders a plain `<a class="mu-dynamic">[live]</a>` link to the target URL instead — but the `refresh`/`fields`/`pid` data isn't thrown away: it's exposed as `data-refresh`, `data-fields`, and `data-pid` attributes on that link, so a consuming web app can wire up its own live-refresh behaviour if it wants to. `refresh` only becomes a `data-refresh` attribute if it parses as a number `>= 1` (matching NomadNet's own "0 or omitted disables it" rule). See [Known limitations](#known-limitations).

### Literal blocks

```
`=
This text is rendered verbatim in a <pre> block.
No Micron formatting is applied inside.
`=
```

Each `` `= `` must be **alone on its own line** — that's the only form NomadNet recognizes as a literal-block toggle. `` `= `` appearing mid-line, with other content around it, isn't special syntax at all; it's just consumed as an unrecognized token like any other.

### Tables

```
`t
| Name | Price | Qty |
| ---- | :---: | --: |
| Apple | Free | 5 |
| Orange | Ask, nicely | 3 |
`t
```

Renders as literal box-drawing-character ASCII art (`┌───┬───┐` borders, padded monospace cells) inside the normal text flow — not a semantic HTML `<table>` — matching what real NomadNet actually shows. The first row is the header (always left-aligned); the second is a markdown-style alignment separator (`:---:` center, `---:` right, anything else left); remaining rows are data. Column width is the widest cell in that column (ignoring Micron formatting tokens for the width calculation, floor of 3 characters); cell text itself still gets parsed normally, so a colour or bold token inside a cell renders correctly. `` `t `` can take an optional alignment letter and/or max-width number right after it (e.g. `` `tc30 ``) to center/right/left-align the whole table and cap its total width — wide tables get their widest columns shrunk down to fit. Use `\|` inside a cell for a literal pipe character.

### Form fields

Fields render as disabled `<input>` elements unless `authenticated=True` is passed to `convert()`.

```
`<name`default>                  Text input — name with optional default value
`<size|name`default>             Text input with character size (e.g. `<20|name`>)
`<!|name`default>                Password input (! flag)
`<?|name|value`label>            Checkbox with label (* pre-checks: `<?|name|value|*`label>)
`<^|name|value`label>            Radio button with label (* pre-selects)
```

The backtick before the closing `>` is mandatory for every field type, including checkbox and radio — `` `<?|name|value> `` without it is not valid Micron and renders as plain text, not an input. This matches NomadNet's own field parser, which gives up entirely when it can't find that backtick.

NomadNet's Guide actually favors leaving the checkbox/radio field's own label empty and writing the visible label as plain text right after the `>` (e.g. `` `<?|name|value`>Label text ``) rather than embedding it inside the field as shown above. Both forms work identically — the parser accepts either — the embedded-label form here is just easier to read in isolation.

## Known limitations

- **Partials render as a static link only** — no actual live auto-refresh happens (the `refresh`/`fields`/`pid` data is exposed via `data-*` attributes for a consuming app to use, but no JS ships with this library). See [Partials](#partials) above.
- **Table column widths use `len()`, not `wcwidth`** — NomadNet's own table renderer consults `wcwidth` for double-width Unicode glyphs; this converter doesn't, to avoid adding a runtime dependency this library has never had. Tables with wide (e.g. CJK) characters in cells may not align columns as precisely as real NomadNet would.
- **The table width-shrink algorithm is a faithful-effort approximation**, not a byte-for-byte port of NomadNet's exact "proportionally shrink the widest columns" formula (which isn't fully specified in the reference source) — it greedily shrinks the single widest column by one character at a time until the table fits.
- **A rare anchor-collision edge case**: the bare `` `[label`#] `` "jump to next heading" link is resolved by a pre-pass that only simulates *other headings* claiming anchor slugs, not explicit `` `:name `` anchors declared during the real render. If an explicit anchor earlier in the document happens to claim the exact slug a later heading would auto-generate, that heading loses its `id` (correct first-wins behavior), but a bare-hash link could still point at `href="#name"` where `name` belongs to the earlier anchor rather than the heading — a nearby, valid target, just not the intended one. Requires a deliberate or coincidental naming collision to trigger.

## Security

All user-supplied content is HTML-escaped before output. The converter is safe to use with untrusted Micron input — XSS via markup is explicitly tested in the test suite.

External URLs are rendered as plain `<a>` links. Links whose resolved path contains a `/file/` segment (NomadNet's download-file convention) are blocked and rendered as `#`. Internal NomadNet links resolve to canonical `hash://` URLs by default — pass a custom `url_resolver` to produce application-relative hrefs instead (see [Custom URL resolution](#custom-url-resolution)).

## Running tests

```bash
pip install pytest
pytest tests/
```

## License

MIT — see [LICENSE](LICENSE).

## Related

- [NomadNet](https://github.com/markqvist/NomadNet) — the NomadNet node software (defines the Micron spec)
- [Ansi2MicronMU](https://github.com/JamesM92/Ansi2MicronMU) — the other direction: convert ANSI terminal output (e.g. from `git log --color`, `htop`, `ls --color`) into Micron. Pair with Micron2HTML to expose existing CLI tools through a NomadNet site or a web frontend:
  ```bash
  git log --color=always | ansi2micron | micron-convert -
  ```
- [NomadDockerNet](https://github.com/JamesM92/NomadDockerNet) — the web browser that uses this library
