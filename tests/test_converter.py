"""Tests for the Micron → HTML converter."""

import pytest
from micron2html.converter import MicronConverter


@pytest.fixture
def conv():
    return MicronConverter()


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

class TestComments:
    def test_comment_line_omitted(self, conv):
        out = conv.convert("# this is a comment")
        assert "comment" not in out
        assert out.strip() == ""

    def test_comment_does_not_consume_next_line(self, conv):
        out = conv.convert("# comment\nhello")
        assert "hello" in out


# ---------------------------------------------------------------------------
# Headings
# ---------------------------------------------------------------------------

class TestHeadings:
    def test_h1(self, conv):
        out = conv.convert("> Title")
        assert 'class="mu-h1"' in out
        assert "Title" in out

    def test_h2(self, conv):
        out = conv.convert(">> Subtitle")
        assert 'class="mu-h2"' in out

    def test_h3(self, conv):
        out = conv.convert(">>> Deep")
        assert 'class="mu-h3"' in out

    def test_heading_level_4_falls_back_to_mu_line(self, conv):
        # NomadNet: only heading1/2/3 styles exist; deeper levels
        # fall back to "plain" rendering (no bg block).
        out = conv.convert(">>>> Level 4")
        assert 'mu-line' in out
        assert 'mu-h4' not in out
        assert 'mu-h3' not in out

    def test_heading_content_parsed(self, conv):
        out = conv.convert("> `!Bold Title`!")
        assert 'class="mu-h1"' in out
        assert "<strong>" in out

    def test_empty_heading_emits_blank_line(self, conv):
        # Deliberate deviation from NomadNet: its parse_line() returns None
        # for an empty heading (no row at all). We render a blank row
        # instead — collapsing the line entirely reads as a bug in HTML.
        out = conv.convert(">")
        assert 'mu-blank' in out


# ---------------------------------------------------------------------------
# Dividers
# ---------------------------------------------------------------------------

class TestDividers:
    def test_single_dash(self, conv):
        out = conv.convert("-")
        assert "<hr" in out

    def test_double_dash(self, conv):
        out = conv.convert("--")
        # `--` is a styled divider in v1.0.2 (preserves `-` for the renderer)
        assert "mu-divider" in out or "mu-hr" in out

    def test_double_equals(self, conv):
        out = conv.convert("-=")
        assert "mu-hr-double" in out

    def test_triple_dash_falls_back_to_default_rule(self, conv):
        # NomadNet only honours a custom divider character when the line is
        # exactly "-" + one more character (MicronParser.py's parse_line:
        # `if len(line) == 2`). "---" is length 3, so it falls back to the
        # default rule rather than being treated as a "-"-repeat divider.
        out = conv.convert("---")
        assert "mu-divider" not in out
        assert "mu-hr-double" not in out
        assert "<hr" in out

    def test_triple_char_equals_falls_back_to_default_rule(self, conv):
        # Same length rule applies to the `-=` "double rule" special case —
        # "-==" is length 3, so it does NOT get the mu-hr-double treatment.
        out = conv.convert("-==")
        assert "mu-hr-double" not in out
        assert "mu-divider" not in out
        assert "<hr" in out

    def test_equals_dash_is_text_not_divider(self, conv):
        # NomadNet: only lines starting with `-` produce dividers.
        # `=-` falls through and renders as regular text.
        out = conv.convert("=-")
        assert "<hr" not in out
        assert "mu-divider" not in out
        assert "=-" in out

    def test_pure_equals_row_stays_as_text(self, conv):
        out = conv.convert("=" * 20)
        assert "<hr" not in out
        assert "=" * 20 in out

    def test_pure_tildes_row_stays_as_text(self, conv):
        out = conv.convert("~" * 20)
        assert "mu-divider" not in out
        assert "~" * 20 in out


# ---------------------------------------------------------------------------
# Inline formatting
# ---------------------------------------------------------------------------

class TestFormatting:
    def test_bold(self, conv):
        out = conv.convert("`!hello`!")
        assert "<strong>" in out
        assert "</strong>" in out
        assert "hello" in out

    def test_italic(self, conv):
        out = conv.convert("`*hello`*")
        assert "<em>" in out
        assert "</em>" in out

    def test_underline(self, conv):
        out = conv.convert("`_hello`_")
        assert "mu-ul" in out

    def test_reset_all(self, conv):
        out = conv.convert("`!bold`")
        assert "<strong>" in out
        assert "</strong>" in out

    def test_backslash_escape(self, conv):
        out = conv.convert("\\`literal backtick")
        assert "`" in out
        assert "<strong>" not in out

    def test_unknown_token_eaten_silently(self, conv):
        # NomadNet: an unrecognized char after a backtick falls through
        # make_output()'s if/elif chain with no output — same outcome as
        # MeshChat's `default: break;`. The rendered text content should
        # have "foo  bar" (with the `> consumed) and no leftover backtick
        # or > glyph.
        import re
        out = conv.convert("foo `> bar")
        # strip all HTML tags to get just the rendered text
        text = re.sub(r'<[^>]+>', '', out)
        assert "foo  bar" in text  # double space where `> was eaten
        assert "`" not in text
        assert ">" not in text


# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------

class TestColors:
    def test_fg_3digit(self, conv):
        out = conv.convert("`Fff0 yellow`f")
        assert "color:#ffff00" in out
        assert "</span>" in out

    def test_bg_3digit(self, conv):
        out = conv.convert("`B333 dark`b")
        assert "background-color:#333333" in out

    def test_invalid_hex_consumes_three_chars(self, conv):
        # NomadNet: F/B always consume 3 chars after the prefix regardless
        # of validity. Invalid hex applies no colour but still eats the
        # 3 chars so they don't leak as text.
        out = conv.convert("`Fxxx hello`f")
        assert "xxx" not in out
        assert "hello" in out

    def test_24bit_T_format_not_supported(self, conv):
        # NomadNet's own reference parser DOES accept `FT<6hex>`, but its
        # Guide.py never teaches it and MeshChat doesn't implement it — we
        # stay 3-hex-only to match what real page authors actually write.
        # The `T` plus 2 next chars are consumed as a (failed) 3-char hex,
        # leaving the tail as visible text.
        out = conv.convert("`FT8b4513 brown`f")
        assert "color:#8b4513" not in out
        assert "color:#" not in out  # no colour applied
        assert "brown" in out

    def test_header_fg_bg_3digit(self, conv):
        out = conv.convert("#!bg=333\n#!fg=aaa\nhello")
        assert "background-color:#333333" in out
        assert "color:#aaaaaa" in out

    def test_header_fg_bg_6digit(self, conv):
        # Unlike the inline `Fxxx`/`Bxxx` tokens (3-hex-only by design),
        # page-level #!bg=/#!fg= headers accept 6-hex too — NomadNet's
        # Guide.py doesn't restrict the header value's length the way it
        # restricts the inline colour tags.
        out = conv.convert("#!bg=112233\n#!fg=aabbcc\nhello")
        assert "background-color:#112233" in out
        assert "color:#aabbcc" in out

    def test_line_level_bg_not_applied_to_div(self, conv):
        # NomadNet: `B` only sets colour state used per text part as it's
        # emitted — a leading B token doesn't fill the entire line, only
        # the explicit span gets the background.
        out = conv.convert("`B400 red `b end")
        # the .mu-line wrapper itself should NOT carry background-color
        assert 'class="mu-line"' in out
        # bg shows up on the <span>, not the line div
        assert 'background-color:#440000' in out
        # extract the .mu-line opening tag and verify no inline bg there
        import re
        m = re.search(r'<div class="mu-line"([^>]*)>', out)
        assert m is not None
        assert 'background-color' not in m.group(1)


# ---------------------------------------------------------------------------
# Alignment
# ---------------------------------------------------------------------------

class TestAlignment:
    def test_center(self, conv):
        out = conv.convert("`c centered text")
        assert "text-align:center" in out

    def test_right(self, conv):
        out = conv.convert("`r right text")
        assert "text-align:right" in out

    def test_left(self, conv):
        out = conv.convert("`l left text")
        assert "text-align:left" in out


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------

class TestLinks:
    def test_basic_link(self, conv):
        out = conv.convert("`[Click here`hash:/abcdef/page.mu]")
        assert "<a " in out
        assert "Click here" in out
        assert "hash://abcdef/page.mu" in out

    def test_custom_url_resolver(self):
        from micron2html import MicronConverter
        def my_resolver(u, n, b):
            return f"/wrap?u={u}"
        c = MicronConverter(url_resolver=my_resolver)
        out = c.convert("`[click`hash:/abcd/page.mu]")
        assert "/wrap?u=hash:/abcd/page.mu" in out

    def test_convert_inline_no_wrapper(self, conv):
        out = conv.convert_inline("hello `!world`!")
        assert "<div" not in out
        assert "<strong>world</strong>" in out

    def test_to_text_strips_formatting(self, conv):
        out = conv.to_text("`!Bold`! and `Fff0 colored`f text")
        assert "<" not in out
        assert "Bold and  colored text" in out

    def test_to_text_strips_headings(self, conv):
        out = conv.to_text(">Title\nbody")
        assert "<" not in out
        assert "Title" in out
        assert "body" in out

    def test_to_text_drops_link_urls(self, conv):
        out = conv.to_text("`[label`https://example.com]")
        assert "label" in out
        assert "example.com" not in out

    def test_link_url_only(self, conv):
        out = conv.convert("`[`hash:/abc/page.mu]")
        assert "<a " in out

    def test_relative_link_with_node_hash(self, conv):
        out = conv.convert("`[About`/about.mu]", node_hash="deadbeef")
        assert "deadbeef" in out

    def test_http_link_passthrough(self, conv):
        out = conv.convert("`[Web`https://example.com]")
        assert 'href="https://example.com"' in out

    def test_link_single_field_spec(self, conv):
        out = conv.convert(
            "`[Register`:/page/index.mu`action=register]",
            node_hash="deadbeef",
        )
        assert 'data-field-spec="action=register"' in out

    def test_link_multi_field_spec_preserves_all(self, conv):
        # Regression: earlier versions only captured parts[2] and dropped
        # every field after the first. The full backtick-separated spec
        # must be preserved so the renderer can forward each key=value.
        out = conv.convert(
            "`[Go`:/page/x.mu`a=1`b=2`c=3]",
            node_hash="deadbeef",
        )
        assert 'data-field-spec="a=1`b=2`c=3"' in out


# ---------------------------------------------------------------------------
# Partials
# ---------------------------------------------------------------------------

class TestPartials:
    def test_partial_renders_live_link(self, conv):
        out = conv.convert("`{hash:/abcdef/status.mu`5}")
        assert "<a " in out
        assert 'class="mu-dynamic"' in out
        assert "[live]" in out
        assert "hash://abcdef/status.mu" in out

    def test_partial_without_refresh_arg(self, conv):
        out = conv.convert("`{hash:/abcdef/status.mu}")
        assert "hash://abcdef/status.mu" in out
        assert "[live]" in out

    def test_partial_fields_and_pid_are_discarded(self, conv):
        # NomadNet's partial fields (pipe-separated, may include pid=) are
        # only meaningful for the live async-refresh behavior this converter
        # doesn't implement — only the URL survives into the rendered link.
        out = conv.convert("`{hash:/abcdef/status.mu`10`action=view|pid=main}")
        assert "hash://abcdef/status.mu" in out
        assert "action=view" not in out
        assert "pid=main" not in out

    def test_partial_unclosed_renders_literal_brace(self, conv):
        out = conv.convert("`{hash:/abcdef/status.mu")
        assert "<a " not in out
        assert "{" in out


# ---------------------------------------------------------------------------
# Literal mode
# ---------------------------------------------------------------------------

class TestLiteral:
    def test_literal_block(self, conv):
        out = conv.convert("`=`!not bold`=`!")
        # The bold token inside literal should appear as text
        assert "&grave;" in out or "`!not bold`!" in out or "`!" in out

    def test_literal_prevents_bold(self, conv):
        out = conv.convert("`= `! `=")
        assert "<strong>" not in out


# ---------------------------------------------------------------------------
# Form fields (read-only rendering)
# ---------------------------------------------------------------------------

class TestFormFields:
    def test_text_field(self, conv):
        # Field syntax requires backtick separator: `<flags|name`default>
        out = conv.convert("`<|username`alice>")
        assert 'input' in out
        assert 'disabled' in out
        assert 'value="alice"' in out

    def test_checkbox_with_label(self, conv):
        # NomadNet: checkbox needs the backtick separator too:
        #   `<?|name|value|*`label>
        out = conv.convert("`<?|agree|yes|*`I agree>")
        assert 'type="checkbox"' in out
        assert 'disabled' in out
        assert 'checked' in out
        assert 'I agree' in out

    def test_radio_with_label(self, conv):
        out = conv.convert("`<^|color|red`Red>")
        assert 'type="radio"' in out
        assert 'value="red"' in out
        assert 'Red' in out

    def test_password_field(self, conv):
        out = conv.convert("`<!|password`secret>")
        assert 'type="password"' in out
        assert 'disabled' in out

    def test_field_without_backtick_separator_is_eaten(self, conv):
        # NomadNet: missing backtick in field syntax causes the whole
        # `< token to be silently consumed (MicronParser.py's field
        # handler gives up when `line.find('`', field_start)` is -1).
        out = conv.convert("`<?|agree|yes|*>")
        # The input opens with `< and never has a backtick before > —
        # parseField would return null, and the < is eaten.
        assert 'type="checkbox"' not in out
        assert '<input' not in out
        # The chars after the eaten `< render as text
        assert 'agree' in out


# ---------------------------------------------------------------------------
# HTML escaping (security)
# ---------------------------------------------------------------------------

class TestEscaping:
    def test_xss_in_text(self, conv):
        out = conv.convert("<script>alert(1)</script>")
        assert "<script>" not in out

    def test_ampersand_escaped(self, conv):
        out = conv.convert("a & b")
        assert "&amp;" in out

    def test_xss_in_link_label(self, conv):
        out = conv.convert('`[<img src=x>`hash:/abc/p.mu]')
        assert "<img" not in out
