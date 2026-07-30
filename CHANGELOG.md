# Changelog

All notable changes to Micron2HTML are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.1.0] - 2026-07-30

### Changed — goal correction: MeshChat parity → NomadNet parity

The project's stated design goal was "MeshChat parity" (matching [Reticulum MeshChat](https://github.com/liamcottle/reticulum-meshchat)'s `MicronParser.js`). That target was corrected to full NomadNet parity — rendering Micron the way the real [NomadNet](https://github.com/markqvist/NomadNet) client would, in both directions, per its own [Guide.py](https://github.com/markqvist/NomadNet/blob/master/nomadnet/ui/textui/Guide.py) (the in-app spec for page authors), [MicronParser.py](https://github.com/markqvist/NomadNet/blob/master/nomadnet/ui/textui/MicronParser.py) (the reference implementation), and RNS's `MarkdownToMicron.format_table_raw` (the table-rendering algorithm), all fetched and read line-by-line for this pass. Most of what was previously justified as "MeshChat parity" turned out to already match NomadNet's own behavior too (unknown-token consumption, the field backtick requirement, heading depth limits, no line-level `B` fill, alignment tokens working anywhere inline) — those comments were relabeled without any behavior change.

**New features, previously unimplemented:**

- **Tables** (`` `t ``). Rendered as literal box-drawing-character ASCII art — the same visual approach real NomadNet uses — not a semantic HTML `<table>`, for genuine visual parity. Supports markdown-style header/separator/data rows, per-column alignment, minimum column width, an optional whole-table alignment + max-width suffix (`` `tc30 ``), and escaped pipes in cell content. Column widths use `len()` rather than `wcwidth` (documented simplification — avoids a new runtime dependency).
- **Anchors** — heading auto-anchors (slugified heading text, e.g. `>Hello World` → `id="hello-world"`), explicit `` `:name `` declarations (zero-width, first-declared-wins shared namespace), `` `[label`#name] `` named jump links, and bare `` `[label`#] `` "jump to the next heading" links. `slugify_micron()` is exported from the package.

**Real, code-level behavior changes** (both reverse previously-shipped, explicitly-tested Micron2HTML-only leniencies/extensions that have no equivalent in real NomadNet):

- **The inline mid-line literal-block toggle is removed.** `` `=...`= `` usable anywhere within a single line was a Micron2HTML-only extension with no real NomadNet equivalent — NomadNet's `` `= `` toggle only fires on a line that is *exactly* `` `= `` and nothing else (the multi-line block form, already correct). `` `=`!not bold`=`! `` now renders "not bold" as **bolded** text (the `` `= `` tokens are silently consumed like any unrecognized token, `` `! `` toggles bold normally around them) instead of suppressing the bold.
- **Link field-specs with more than 3 backtick-separated segments now render nothing at all**, matching NomadNet exactly (`` `[label`url`a=1`b=2`c=3] `` → no `<a>` tag, not even fallback text). This reverses a v1.0.3 fix that leniently joined the extra segments back together — that fix was solving a MeshChat-specific quirk, not real NomadNet behavior (NomadNet's own link parser sets the URL to empty and skips emitting anything when there are more than 3 components). The correct, NomadNet-native way to pass multiple fields — a single pipe-separated segment (`` `[label`url`a=1|b=2|c=3] ``) — is unaffected and unchanged.
- **Empty heading lines now emit nothing** (no row, no blank space), matching NomadNet's `parse_line()` returning `None`. Reverses a deliberate deviation made earlier in this same body of work (rendering a visible blank row) once the broader goal was clarified to be exact parity rather than "whatever reads best in isolation."

**Partials get richer, still without shipping JS:**

- `` `{url`refresh`fields} ``'s `refresh` and `fields` (pipe-separated, may include `pid=`) components — previously silently discarded — are now exposed as `data-refresh`, `data-fields`, and `data-pid` attributes on the rendered link, so a consuming web app can wire up its own live-refresh behavior if it wants to. `refresh` only becomes `data-refresh` if it parses as a number `>= 1`, matching NomadNet's own "0 or omitted disables it" rule. Still no live refresh happens inside this library itself — that would require shipping JS, which this pure-Python library never has.

**Docs corrected to match:**

- Checkbox/radio field docs now also show NomadNet's own canonical style (empty field label, visible text written after the `>`) alongside the embedded-label form.
- Link field-specs' primary documented syntax is now pipe-separated (`` `[label`url`a=1|b=2] ``), matching NomadNet's actual syntax.
- README's "Known limitations" no longer lists tables, anchors, or "alignment tags must appear at line start" (the last of those was never a real parser rule to begin with — Guide.py's line-start wording is author style advice, not something `make_output()` actually enforces; Micron2HTML already matched real NomadNet's permissive behavior there). What's left: the partials live-refresh gap, the `wcwidth` and table-shrink-formula approximations, and a rare anchor-collision edge case in the bare-hash pre-pass — see README for details.

See [README.md](README.md) for the full corrected syntax reference.

### Fixed

- **Out-of-order tag closes produced mismatched HTML nesting.** `_close_innermost()`/`_pop_tag()` (used by `` `b ``/`` `f `` and the `` `! ``/`` `_ ``/`` `* `` toggles) searched the open-tag stack for the target type and popped it from the middle when it wasn't actually innermost, but still emitted the close tag at the *current* output position — which a browser applies LIFO, so it closed whatever tag genuinely was innermost instead. Example: `` `B777 X`f `F975`b <> `` opened a background span, then a foreground span, then tried to close the background — the emitted `</span>` actually closed the (empty) foreground span in the DOM, leaving the background open until end-of-line and desyncing the internal bookkeeping for the rest of the run. Fixed by having `_close_innermost()` unwind: close every tag above the target (innermost-first), close the target, then reopen the unwound tags as fresh elements. The tag stack now stores each entry's opening HTML alongside its closing HTML (`(type, open_html, close_html)`, was `(type, close_html)`) so it can replay the reopens; `_pop_tag()` is gone, the `` `! ``/`` `_ ``/`` `* `` branches route through `_close_innermost()` like `` `b ``/`` `f `` always did instead of inlining their own close+pop. Reported against a downstream consumer (vscode-mu-preview) as "background color not resetting after `` `b `` token" — confirmed the bug was entirely upstream here, not in the .mu source or the downstream renderer. 4 new tests in `TestTagNesting` cover the reported repro, a bold/colour interleave, a triple-nested two-level unwind, and the already-correct non-interleaved baseline.
- **README form-field docs described broken checkbox/radio syntax.** `` `<?|name|value> `` and `` `<^|name|value> `` (no backtick before the closing `>`) look plausible but don't actually render as `<input>` elements — NomadNet's own field parser requires the backtick + label, e.g. `` `<?|name|value`label> ``. [examples/showcase.mu](examples/showcase.mu) had the same broken form. Both corrected; the mandatory-backtick rule is now called out explicitly.
- **README security section mischaracterized the file-link block.** Said `file://` scheme links are blocked; the code actually blocks any resolved URL containing a `/file/` path segment (NomadNet's download-file convention) — an actual `file://` URL isn't specially handled. Wording corrected, and the default `hash://`-vs-custom-resolver distinction is now spelled out.
- **README said "pure Python 3.9+".** `pyproject.toml` has required `>=3.10` since v1.0.8; README now matches.
- **Removed stale docs for the dropped `` `FTxxxxxx ``/`` `BTxxxxxx `` inline format.** The 24-bit inline extension was removed from the parser in v1.0.2, but [README.md](README.md) and [examples/showcase.mu](examples/showcase.mu) still described/demonstrated it. Docs and the example page now only show the supported 3-hex shorthand.
- **README's `` `Fxxx `` doubling example was missing the command letter.** Showed `F40 → #ff4400` (2 hex digits after a bare `F`, which doesn't match the actual 3-hex format); corrected to `` `FF40 → #ff4400 ``.

### Added

- **README documents `to_text()` and `--format text`.** Both existed and were tested but were never mentioned in the library/CLI usage sections.
- **README documents the partials token** (`` `{URL`refresh`fields} ``), previously present in the parser with no docs and no test coverage.
- **37 new tests**: `TestTables` (13), `TestHeadingAnchors`/`TestExplicitAnchors`/`TestAnchorLinks` (18), `TestTagNesting` (4), divider length-2 rule (2), plus rewrites of the tests covering every behavior change above (empty headings, partials data-attributes, literal-toggle removal, link field-spec strictness). Test suite: 57 → 94.

### Infrastructure

- **`ci.yml` now also runs on pushes to `dev`.** Previously only `main` pushes and PRs into `main` triggered the test/build workflow, so `dev`'s tip went unverified until promoted. `security.yml` (pip-audit/CodeQL) stays on the main+PR path only.

## [1.0.8]

### Changed

- **Python support window updated:** dropped Python 3.9 (EOL October 2025), added Python 3.13 and 3.14. `requires-python` is now `>=3.10`. Classifiers and the CI test matrix updated to match.
- **Stricter field-spec width parsing.** [converter.py](converter.py) field-spec width parsing now uses an `isdigit()` guard instead of a `try / except ValueError`. Behavior is unchanged for any well-formed Micron input. Edge case: previously a leading sign (`+5`, `-5`) or whitespace would have been accepted by `int()`; these now correctly fall back to the default width. Resolves CodeQL `py/empty-except` quality alert at the source rather than documenting around it.

### Infrastructure

- Bumped all GitHub Actions to their current major versions (Node 24 runtime): `actions/checkout` v4 → v6, `actions/setup-python` v5 → v6, `actions/upload-artifact` v4 → v7, `actions/dependency-review-action` v4 → v5, `github/codeql-action` v3 → v4.
- Enabled GitHub Dependency Graph + Dependabot security alerts on the repository so the `dependency-review` PR check actually runs (previously failing silently with a setup error).
- Added Dependabot config (monthly cadence for `pip` + `github-actions`).
- Added CI / Security / PyPI / Python-version badges to the README.
- Branch protection on `main` requires the CI matrix, build, pip-audit, and CodeQL checks to pass.

## [1.0.7]

### Infrastructure

- Added GitHub Actions CI: pytest matrix across Python 3.9–3.12, sdist + wheel build, and `twine check`.
- Added security workflow: `pip-audit` for dependency CVEs, GitHub `dependency-review` on PRs, and CodeQL static analysis with `security-and-quality` queries, plus a weekly scheduled run to catch newly-disclosed vulnerabilities.
- Added PyPI publish workflow using Trusted Publishing (OIDC) — releases are built and uploaded automatically on GitHub Release publication, with no long-lived API tokens stored in the repo.

No functional code changes since 1.0.6.

## [1.0.5]

### Changed

- **Braille (U+2800–U+28FF) is now CSS-drawn instead of font-rendered.**
  v1.0.4 routed the Braille block through a system-font fallback chain,
  but Roboto Mono Nerd Font has no Braille glyphs at all and the chosen
  fallbacks (Noto Sans Mono, DejaVu Sans Mono, Noto Sans Symbols 2)
  render Braille narrower than the monospace cell — adjacent cells
  leave visible gaps and a row of full-dot Braille reads as separated
  dots instead of a contiguous grid. The converter now replaces every
  Braille character with `<span class="mu-braille" style="--mu-braille-dots:…">`,
  with the raised dots encoded as a list of `radial-gradient`s. The
  bundled `micron-meshchat.css` ships the matching `.mu-braille` rule
  (1ch-wide inline-block + ::before painting the gradients). Result:
  paired dots within a cell read as paired, rows of identical cells
  flow as a continuous strip, and rendering is fully font-independent.
  License + bundle size unchanged (font-bundling alternatives explored
  in v1.0.4 were dropped).

  Public-API addition: `MicronConverter.convert()` and `convert_inline()`
  gain a `render_braille: bool = True` parameter — pass `False` to keep
  the raw Braille codepoints (e.g. when feeding the result through a
  pipeline that strips HTML tags). `to_text()` does this internally so
  Braille survives the strip.

## [1.0.4]

### Fixed

- **Braille (U+2800-28FF) now renders without gaps between cells.** Roboto Mono Nerd Font's Braille glyphs don't reach the cell edges, so a row of full-dot Braille displayed as gappy dots instead of a contiguous grid — visible mismatch with MeshChat, which routes Braille through a system font that fills the cell. The bundled `micron-meshchat.css` now carves U+2800-28FF out of the Roboto Mono `@font-face` via `unicode-range` and adds a second `@font-face` fallback chain (Noto Sans Mono → DejaVu Sans Mono → Symbola → Apple Symbols → Segoe UI Symbol). Pure-CSS, no font bundled, zero added bytes — and if none of the fallbacks are installed the browser drops to its generic monospace, which is no worse than before.

## [1.0.3]

### Changed (breaking)

- **Bundled stylesheet renamed from `micron.css` to `micron-meshchat.css`** to make the MeshChat-parity intent explicit. If you previously linked the file by name in your HTML or copied it during your build, update the path.

### Fixed

- **Multi-field link specs no longer drop fields after the first.** `[label`URL`a=1`b=2]` previously took only `parts[2]` as the field spec, silently discarding `b=2`. The renderer now joins all backtick-separated field specs into `data-field-spec`, matching MeshChat's behaviour. Single-field links (the common case) are unchanged.

## [1.0.2]

### Changed — MeshChat parity pass

The renderer was audited line-by-line against [Reticulum MeshChat](https://github.com/liamcottle/reticulum-meshchat)'s `MicronParser.js` so the same Micron source produces equivalent output in both renderers.

- **Unknown tokens after `` ` `` are now silently consumed.** Previously the converter emitted a literal backtick and reprocessed the next char; MeshChat's parser silently drops both (its `default: break;` branch). Use `` \\` `` to render a literal backtick.
- **`=-` no longer matches as a divider.** Only lines starting with `-` produce dividers — `=-` falls through and renders as text. Mirrors MeshChat's `if (line[0] === "-")` check.
- **Line-level background-colour extraction removed.** `_extract_line_bg_color()` is gone; a leading `` `B<color> `` no longer fills the entire row, only the explicit `<span>` segment. MeshChat doesn't apply line-level bg.
- **24-bit `` `FT<6hex> `` colour format dropped.** MeshChat's parser only handles 3-char colours. The `T` prefix and following 2 chars are now consumed as a (failed) 3-char hex match — the 3 chars are still eaten so they don't leak as visible text.
- **Invalid hex still consumes 3 chars.** `` `Fxxx `` / `` `Bxxx `` always advance 3 characters after the prefix, with or without valid hex, matching MeshChat's `line.substr(i+1,3); skip = 3;`.
- **Section indent off-by-one corrected.** Body lines and dividers now use `(section - 1) * 20px` (matching MeshChat's `applySectionIndent`). Previously they used `section * 20px`, indenting one level too deep.
- **Indent uses `margin-left` consistently** across headings, body lines, dividers, and literal blocks (was a mix of `padding-left` / `margin-left`).
- **Empty heading line emits `<div class="mu-blank"></div>`** instead of dropping the line entirely. MeshChat's `parseLine` returns null for empty headings and the outer loop appends a `<br>`.
- **Heading levels 4+ render as `mu-line`.** Only `mu-h1`, `mu-h2`, `mu-h3` get the bg-block style; `>>>>` and beyond fall back to plain rendering, matching MeshChat's `STYLES_DARK` which only defines `heading1/2/3`.
- **Heading bg always extends to the container's left edge.** The heading text is offset via `padding-left: (level - 1) * 20px`, but the bg-block itself starts at column 0 regardless of section depth — visually consistent with MeshChat's full-width heading bars.
- **Literal blocks now carry section indent.** `<pre class="mu-literal">` gets `margin-left: (section - 1) * 20px` so multi-line code/diagram blocks under a `>>` heading indent the same as surrounding body text.
- **Field syntax now requires a backtick separator** between flags|name and the default/label, matching MeshChat's `parseField`. The signature of `_render_field()` changed to take `field_content` and `field_data` as separate arguments. Malformed fields (no backtick before `>`) cause the `` `< `` to be silently eaten — same broken behaviour as MeshChat, useful for cross-renderer parity testing.

### Removed

- Public-API surface: `_extract_line_bg_color()` and the 24-bit `T<6hex>` branch of `_parse_color()` are gone.
- `_render_field(inner, authenticated)` → `_render_field(field_content, field_data, authenticated)`. Internal helper but worth flagging if any downstream code calls it.

### Tests

- 47 tests in `tests/test_converter.py`, all passing. New cases cover: empty heading → blank, `=-` as text, pure `=`/`~` rows as text, unknown-token consumption, invalid hex 3-char consume, 24-bit format dropped, line-level bg removed, h4 fallback to plain, field-without-backtick eaten.

### Stylesheet & font

- `micron.css` reworked to match MeshChat's rendering — pure `#000` page bg, `#dddddd` body text, MeshChat-parity heading bg-blocks (`#bbb`/`#999`/`#777`), Roboto Mono Nerd Font as the primary face, and the line-gap fix (`-1.08em` margin-bottom on every block element) so box-drawing rows touch.
- `RobotoMonoNerdFont-Regular.ttf` is now bundled with the package — drop in `micron.css` alongside the converter output and the `@font-face` rule picks up the bundled font automatically. Adds ~2.4 MB to the wheel.
- Bold rendering uses a `text-shadow` fake-bold so glyph widths are preserved (only the Regular weight ships); `font-synthesis-weight: none` blocks faux bold from breaking monospace alignment.
- Long Micron lines no longer wrap — content scrolls horizontally inside `.mu-page` so ASCII art and box diagrams stay aligned at any viewport width.

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
