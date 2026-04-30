# Changelog

All notable changes to Micron2HTML are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0]

Initial public release. The project was previously developed under the name `micron-converter` as an internal helper for [NomadDockerNet](https://github.com/JamesM92/NomadDockerNet); v1.0.0 is the first release as a standalone library suitable for use by other projects.

### Public API

- `MicronConverter` — class with three rendering methods:
  - `convert(text, node_hash, base_path, authenticated)` — full Micron document → HTML fragment
  - `convert_inline(text, ...)` — single line of Micron → inline HTML (no `<div class="mu-line">` wrapper); use for titles, brand strings, message previews
  - `to_text(text)` — Micron → plain text with all formatting and colours stripped; use for previews, search indexing, accessibility
- `default_url_resolver(url, node_hash, base_path)` — module-level function exported for composition by custom resolvers
- `UrlResolver` — type alias for the resolver callback signature
- `__version__ = "1.0.0"`

### Features

- **Pluggable URL resolution.** Pass a `url_resolver` callback to `MicronConverter()` to control how Micron URLs become hrefs. The library default emits canonical `hash://...` URLs; web frontends typically wrap that with their own URL pattern.
- **Bundled stylesheet.** `micron.css` ships with the package, scoped to `.mu-*` classes — drop it into your static directory for instant NomadNet terminal aesthetics.
- **CLI tool** (`micron-convert`) supports `--format html|text`, `--fragment`, `--node-hash`, and writes a fully-styled HTML page using the bundled stylesheet by default.
- **Reference example** at `examples/showcase.mu` demonstrating every feature.
- **Comprehensive tests** — 38 tests covering comments, headings, formatting, colors, dividers, links, literal blocks, alignment, form fields, HTML escaping (XSS safety), custom URL resolvers, and the inline/text rendering modes.
- **Pure Python**, zero runtime dependencies, supports Python 3.9+.

### Security

All user-supplied content is HTML-escaped. File-download URLs are blocked. XSS via Micron markup is explicitly tested.
