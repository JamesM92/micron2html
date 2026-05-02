# Micron2HTML

A Python library and CLI tool that converts [Micron](https://github.com/markqvist/NomadNet) markup to HTML.

Micron is the terminal markup language used by [NomadNet](https://github.com/markqvist/NomadNet) nodes. This library lets you render Micron pages in web browsers and other HTML-capable environments.

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

No runtime dependencies — pure Python 3.9+.

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

A MeshChat-parity stylesheet ships with the package, named to make the design intent explicit:

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
```

## Micron syntax

### Comments and headers

```
# This is a comment — the whole line is stripped from output

#!bg=2a2a2a   Set page background colour (3 or 6 hex digits)
#!fg=aaaaaa   Set page foreground colour
```

### Headings and sections

```
>Section heading      h1
>>Subsection          h2
>>>Sub-subsection     h3
```

### Dividers

```
---     Horizontal rule
-=      Double horizontal rule
-<x>    Styled divider — repeats character `x` (e.g. -* renders centred * row)
```

### Inline formatting

```
`!text`!      Bold
`*text`*      Italic
`_text`_      Underline

`Fxxx         Set foreground colour (3-hex shorthand: each digit doubled — F40 → #ff4400)
`FTxxxxxx     Set foreground colour (6-hex true colour)
`f            Reset foreground colour to default

`Bxxx         Set background colour (3-hex shorthand)
`BTxxxxxx     Set background colour (6-hex)
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
`<name`default>             Text input — name with optional default value
`<size|name`default>        Text input with character size (e.g. `<20|name`>)
`<!|name`default>           Password input (! flag)
`<?|name|value>             Checkbox (* at end pre-checks: `<?|name|value|*>)
`<^|name|value>             Radio button (* at end pre-selects)
```

## Security

All user-supplied content is HTML-escaped before output. The converter is safe to use with untrusted Micron input — XSS via markup is explicitly tested in the test suite.

External URLs are rendered as plain `<a>` links. File download links (`file://`) are blocked. Internal NomadNet links are resolved to application-relative hrefs.

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
