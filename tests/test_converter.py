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

    def test_heading_content_parsed(self, conv):
        out = conv.convert("> `!Bold Title`!")
        assert 'class="mu-h1"' in out
        assert "<strong>" in out


# ---------------------------------------------------------------------------
# Dividers
# ---------------------------------------------------------------------------

class TestDividers:
    def test_single_dash(self, conv):
        out = conv.convert("-")
        assert "<hr" in out

    def test_double_dash(self, conv):
        out = conv.convert("--")
        assert "<hr" in out

    def test_double_equals(self, conv):
        out = conv.convert("-=")
        assert "mu-hr-double" in out


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
        # After reset, strong should be closed
        assert "<strong>" in out
        assert "</strong>" in out

    def test_backslash_escape(self, conv):
        out = conv.convert("\\`literal backtick")
        assert "`" in out
        assert "<strong>" not in out


# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------

class TestColors:
    def test_fg_3digit(self, conv):
        out = conv.convert("`Fff0 yellow`f")
        assert "color:#ffff00" in out
        assert "</span>" in out

    def test_fg_6digit(self, conv):
        out = conv.convert("`FT00ff00 green`f")
        assert "color:#00ff00" in out

    def test_bg_3digit(self, conv):
        out = conv.convert("`B333 dark`b")
        assert "background-color:#333333" in out

    def test_bg_6digit(self, conv):
        out = conv.convert("`BT1a1a1a dark`b")
        assert "background-color:#1a1a1a" in out


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
        out = conv.convert("`<|username`>")
        assert 'input' in out
        assert 'disabled' in out

    def test_checkbox(self, conv):
        out = conv.convert("`<?|agree|yes>")
        assert 'type="checkbox"' in out
        assert 'disabled' in out

    def test_password_field(self, conv):
        out = conv.convert("`<!|password`>")
        assert 'type="password"' in out
        assert 'disabled' in out


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
