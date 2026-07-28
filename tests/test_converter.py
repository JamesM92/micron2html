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

    def test_empty_heading_emits_nothing(self, conv):
        # NomadNet: parse_line() returns None for an empty heading — no
        # row, no blank space.
        out = conv.convert(">")
        assert 'mu-blank' not in out
        assert out.strip() == ""


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

    def test_header_fg_bg_6digit_not_supported(self, conv):
        # Deliberately 3-hex-only, same as the inline colour tags: with no
        # marker distinguishing 3-hex from 6-hex, allowing both would make
        # a value's meaning depend silently on its length. NomadNet's own
        # docs would technically permit 6-hex here, but we don't chase it.
        out = conv.convert("#!bg=112233\n#!fg=aabbcc\nhello")
        assert "background-color" not in out
        assert "color:#" not in out

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

    def test_link_multi_field_spec_uses_pipes_not_extra_backticks(self, conv):
        # NomadNet-native form: multiple fields go in ONE backtick-delimited
        # segment, pipe-separated.
        out = conv.convert(
            "`[Go`:/page/x.mu`a=1|b=2|c=3]",
            node_hash="deadbeef",
        )
        assert 'data-field-spec="a=1|b=2|c=3"' in out

    def test_link_with_more_than_three_backtick_segments_renders_nothing(self, conv):
        # NomadNet: more than 3 backtick-separated components makes the
        # whole link vanish (link_url = ""), not a leniently-joined spec.
        # This reverses a v1.0.3 fix that was solving a MeshChat-specific
        # leniency, not real NomadNet behavior.
        out = conv.convert(
            "`[Go`:/page/x.mu`a=1`b=2`c=3]",
            node_hash="deadbeef",
        )
        assert "<a" not in out


# ---------------------------------------------------------------------------
# Anchors
# ---------------------------------------------------------------------------

class TestHeadingAnchors:
    def test_heading_auto_anchor_slug(self, conv):
        out = conv.convert("> Hello World")
        assert 'id="hello-world"' in out

    def test_heading_auto_anchor_strips_formatting_tokens(self, conv):
        out = conv.convert("> `!Bold`! Heading")
        assert 'id="bold-heading"' in out

    def test_heading_auto_anchor_ampersand_and_punctuation(self, conv):
        out = conv.convert("> Introduction & Setup")
        assert 'id="introduction-setup"' in out

    def test_heading_level_4_also_gets_auto_anchor(self, conv):
        out = conv.convert(">>>> Deep Heading")
        assert 'id="deep-heading"' in out

    def test_heading_auto_anchor_collision_first_wins(self, conv):
        out = conv.convert("> Same\n> Same")
        assert out.count('id="same"') == 1

    def test_empty_heading_no_anchor(self, conv):
        out = conv.convert("> ")
        assert 'id="' not in out


class TestExplicitAnchors:
    def test_explicit_anchor_zero_width(self, conv):
        out = conv.convert("`:mark hello")
        assert 'id="mark"' in out
        assert 'class="mu-anchor"' in out
        assert "hello" in out

    def test_explicit_anchor_name_terminates_at_delimiter(self, conv):
        out = conv.convert("`:foo-bar baz")
        assert 'id="foo-bar"' in out

    def test_explicit_anchor_alone_on_empty_line(self, conv):
        out = conv.convert("`:onlyanchor")
        assert 'id="onlyanchor"' in out

    def test_explicit_and_heading_anchors_share_namespace(self, conv):
        out = conv.convert("`:shared marker\n> Shared")
        assert out.count('id="shared"') == 1

    def test_multiple_explicit_anchors_on_one_line(self, conv):
        out = conv.convert("`:first x `:second y")
        assert 'id="first"' in out
        assert 'id="second"' in out

    def test_explicit_anchor_name_stops_before_special_chars(self, conv):
        out = conv.convert("`:foo<script>alert(1)</script>")
        assert 'id="foo"' in out
        assert "<script>" not in out
        assert "&lt;script&gt;" in out


class TestAnchorLinks:
    def test_named_anchor_link_href(self, conv):
        out = conv.convert("`[Jump`#install-notes]")
        assert 'href="#install-notes"' in out

    def test_named_anchor_link_forward_reference_resolves(self, conv):
        out = conv.convert("`[Jump`#later-section]\ntext\n> Later Section")
        assert 'href="#later-section"' in out
        assert 'id="later-section"' in out

    def test_bare_hash_link_jumps_to_next_heading(self, conv):
        out = conv.convert("`[Continue`#]\ntext\n> Next Section")
        assert 'href="#next-section"' in out

    def test_bare_hash_link_no_following_heading_falls_back(self, conv):
        out = conv.convert("`[Continue`#]\ntext")
        assert 'href="#"' in out

    def test_bare_hash_link_skips_its_own_heading_line(self, conv):
        out = conv.convert("> Heading with `[link`#] inside\n> Next")
        assert 'href="#next"' in out

    def test_convert_inline_bare_hash_link_does_not_crash(self, conv):
        out = conv.convert_inline("`[x`#]")
        assert 'href="#"' in out


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

_TABLE_MU = (
    "`t\n"
    "| Name | Price | Qty |\n"
    "| ---- | :---: | --: |\n"
    "| `F3a3Apple`f | Free | `!5`! |\n"
    "| Orange | Ask, nicely | 3 |\n"
    "`t"
)


class TestTables:
    def test_basic_table_renders_box_drawing(self, conv):
        out = conv.convert(_TABLE_MU)
        for ch in "┌┐└┘│┬┴┼":
            assert ch in out
        assert "Apple" in out
        assert "Free" in out
        assert "Orange" in out

    def test_table_cell_formatting_renders(self, conv):
        out = conv.convert(_TABLE_MU)
        assert 'color:#33aa33' in out
        assert "<strong>5</strong>" in out

    def test_table_header_always_left_aligned(self, conv):
        out = conv.convert(_TABLE_MU)
        assert "│ Name   │" in out

    def test_table_column_right_and_center_alignment(self, conv):
        out = conv.convert(_TABLE_MU)
        assert "│   3 │" in out  # Qty column, right-aligned
        assert "│    Free" in out  # Price column, center-aligned

    def test_table_min_column_width_three(self, conv):
        out = conv.convert("`t\n| A | B |\n| --- | --- |\n| 1 | 2 |\n`t")
        assert "───" in out  # 1-char columns still pad to width >= 3

    def test_table_width_shrink_on_max_width_suffix(self, conv):
        import re
        out = conv.convert(
            "`t15\n| VeryLongHeader | AnotherVeryLongOne |\n| --- | --- |\n"
            "| xxxxxxxxxxxxxxxxxxxx | yyyyyyyyyyyyyyyyyyyy |\n`t"
        )
        for line in out.split("</div>"):
            visible = re.sub(r"<[^>]+>", "", line)
            assert len(visible) <= 20  # generous slack for the │ borders

    def test_table_wrapped_in_mu_table_div(self, conv):
        out = conv.convert(_TABLE_MU)
        assert 'class="mu-table"' in out

    def test_table_align_wraps_whole_table_and_resets(self, conv):
        out = conv.convert("`tc\n| A | B |\n| --- | --- |\n| 1 | 2 |\n`t\nafter")
        table_part, after_part = out.split("after")
        assert "text-align:center" in table_part
        assert "text-align:center" not in after_part

    def test_table_escaped_pipe_in_cell_not_split(self, conv):
        out = conv.convert("`t\n| A | B |\n| --- | --- |\n| x\\|y | 2 |\n`t")
        assert "x|y" in out

    def test_unclosed_table_flushes_at_eof(self, conv):
        out = conv.convert("`t\n| A | B |\n| --- | --- |\n| 1 | 2 |")
        assert 'class="mu-table"' in out
        assert "┌" in out and "┘" in out

    def test_table_inside_section_indents(self, conv):
        out = conv.convert(">> Section\n`t\n| A | B |\n| --- | --- |\n| 1 | 2 |\n`t")
        assert "margin-left:20px" in out

    def test_empty_table_renders_nothing(self, conv):
        out = conv.convert("`t\n`t")
        assert out.strip() == ""

    def test_table_body_lines_not_interpreted_as_micron(self, conv):
        out = conv.convert(
            "`t\n| A | B |\n| --- | --- |\n| > Not a heading | 2 |\n`t"
        )
        assert "mu-h1" not in out
        assert "&gt; Not a heading" in out


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

    def test_partial_fields_and_pid_are_exposed_as_data_attrs(self, conv):
        # No live-refresh JS is shipped, but the refresh/fields/pid data is
        # exposed via data-* attributes so a consuming web app can wire up
        # its own refresh behaviour if it wants to.
        out = conv.convert("`{hash:/abcdef/status.mu`10`action=view|pid=main}")
        assert "hash://abcdef/status.mu" in out
        assert 'data-refresh="10.0"' in out
        assert 'data-fields="action=view|pid=main"' in out
        assert 'data-pid="main"' in out

    def test_partial_refresh_below_one_is_disabled(self, conv):
        # NomadNet: a refresh value < 1 (including 0) disables refresh
        # entirely — not just "falsy", an explicit threshold.
        out = conv.convert("`{hash:/abcdef/status.mu`0.5}")
        assert "data-refresh" not in out

    def test_partial_unclosed_renders_literal_brace(self, conv):
        out = conv.convert("`{hash:/abcdef/status.mu")
        assert "<a " not in out
        assert "{" in out


# ---------------------------------------------------------------------------
# Literal mode
# ---------------------------------------------------------------------------

class TestLiteral:
    def test_inline_backtick_equals_is_not_a_literal_toggle(self, conv):
        # NomadNet: `= only has meaning as a WHOLE line by itself (handled
        # in _process_line's multi-line block form). Mid-line, it's just an
        # unrecognized token — silently consumed like any other — so `!
        # still toggles bold normally around it. This is a behavior change
        # from an earlier Micron2HTML-only extension (undocumented inline
        # literal toggling) that had no real-NomadNet equivalent.
        out = conv.convert("`=`!not bold`=`!")
        assert "<strong>not bold</strong>" in out

    def test_inline_backtick_equals_does_not_suppress_bold(self, conv):
        out = conv.convert("`= `! `=")
        assert "<strong>" in out


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
