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

#!bg=2a2a2a   Set page background colour (3 or 6 hex digits)
#!fg=aaa      Set page foreground colour
```

Unlike the inline `` `Fxxx ``/`` `Bxxx `` tags below, these headers aren't restricted to 3-hex — NomadNet's Guide gives a 3-hex example but doesn't state a length restriction, and both forms render correctly.

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

Links can also submit form-field data to a node-side page: `` `[Label`url`fields] ``, where `fields` is a single pipe-separated segment — `*` (submit every field on the page), field names to include (`username|auth_token`), or literal `key=value` pairs, mixable in any order (`*|action=preview|id=42`). The parsed spec is emitted verbatim as `data-field-spec` for the consuming application to read. Micron2HTML is also lenient about extra backtick-separated segments after the fields (`` `[Label`url`a=1`b=2] ``) and joins them back together rather than dropping the link — real NomadNet renders nothing at all for that malformed form, so stick to pipes for anything meant to work across clients.

### Partials

```
`{URL}                                Partial with no auto-refresh
`{URL`refresh}                        Partial that re-fetches every `refresh` seconds (0 or omitted disables it)
`{URL`refresh`field1|field2|pid=x}    Partial with request fields; `pid=` targets a specific partial for refresh
```

In real NomadNet, a partial asynchronously loads a fragment of another page and (optionally) re-fetches it in place on an interval — see NomadNet's Guide, "Partials" section. That's not something a one-shot markup→HTML conversion can reproduce without adding JavaScript, so Micron2HTML renders a plain `<a class="mu-dynamic">[live]</a>` link to the target URL instead. The `refresh` and `field`/`pid` components are discarded entirely — only the URL is used. See [Known limitations](#known-limitations).

### Literal blocks

```
`=
This text is rendered verbatim in a <pre> block.
No Micron formatting is applied inside.
`=
```

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

Syntax NomadNet supports that this converter doesn't implement, or implements as a deliberate simplification:

- **Tables** (`` `t ``/`` `t ``-wrapped markdown-style tables) — not implemented. A `` `t `` line currently renders as plain text.
- **Anchors** — auto-anchors from heading slugs, explicit `` `:name `` declarations, and `` `[label`#name] ``/`` `[label`#] `` jump links are not implemented. Links with a `#`-prefixed URL resolve like any other relative link rather than scrolling to a page position.
- **Partials** — implemented as a static link only; no auto-refresh, no request fields. See [Partials](#partials) above.
- **Alignment tags must appear at the start of a line** per NomadNet's Guide; this converter accepts `` `c ``/`` `l ``/`` `r ``/`` `a `` anywhere inline. This is a superset of NomadNet's behavior (it accepts more input, not less), so correctly-authored NomadNet pages aren't affected.
- **The literal-block toggle `` `= `` only fires on a line that is *exactly* `` `= `` and nothing else** in NomadNet; this converter also supports it as an inline mid-line toggle. Same superset relationship as above.

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
