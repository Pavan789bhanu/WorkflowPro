"""Tests for workflow_executor helpers — specifically _markdown_to_html."""

import pytest

from app.services.workflow_executor import _markdown_to_html


class TestMarkdownToHtml:
    """Cover every branch of the tiny dependency-free renderer."""

    # ------------------------------------------------------------------
    # Headings
    # ------------------------------------------------------------------

    def test_h1(self):
        assert "<h1>Title</h1>" in _markdown_to_html("# Title")

    def test_h2(self):
        assert "<h2>Section</h2>" in _markdown_to_html("## Section")

    def test_h3(self):
        assert "<h3>Sub</h3>" in _markdown_to_html("### Sub")

    # ------------------------------------------------------------------
    # Inline formatting
    # ------------------------------------------------------------------

    def test_bold(self):
        html = _markdown_to_html("**important**")
        assert "<strong>important</strong>" in html

    def test_inline_code(self):
        html = _markdown_to_html("`code`")
        assert "<code>code</code>" in html

    def test_bold_and_code_combined(self):
        html = _markdown_to_html("Use **`--flag`** here")
        assert "<strong>" in html
        assert "<code>" in html

    # ------------------------------------------------------------------
    # Unordered lists
    # ------------------------------------------------------------------

    def test_bullet_dash_list(self):
        md = "- Alpha\n- Beta\n- Gamma"
        html = _markdown_to_html(md)
        assert html.count("<ul>") == 1
        assert html.count("</ul>") == 1
        assert "<li>Alpha</li>" in html
        assert "<li>Beta</li>" in html
        assert "<li>Gamma</li>" in html

    def test_bullet_star_list(self):
        md = "* One\n* Two"
        html = _markdown_to_html(md)
        assert "<ul>" in html
        assert "<li>One</li>" in html

    def test_unordered_list_not_wrapped_in_ol(self):
        html = _markdown_to_html("- item")
        assert "<ol>" not in html

    # ------------------------------------------------------------------
    # Ordered lists
    # ------------------------------------------------------------------

    def test_numbered_list(self):
        md = "1. First\n2. Second\n3. Third"
        html = _markdown_to_html(md)
        assert "<ol>" in html
        assert "</ol>" in html
        assert "<li>First</li>" in html
        assert "<li>Second</li>" in html
        assert "<li>Third</li>" in html

    def test_numbered_list_uses_ol_not_ul(self):
        html = _markdown_to_html("1. Step one\n2. Step two")
        assert "<ol>" in html
        assert "<ul>" not in html

    def test_numbered_list_single_item(self):
        html = _markdown_to_html("1. Only item")
        assert "<ol>" in html
        assert "<li>Only item</li>" in html

    # ------------------------------------------------------------------
    # Mixed list types — transition between ol and ul
    # ------------------------------------------------------------------

    def test_mixed_unordered_then_ordered(self):
        md = "- Bullet one\n- Bullet two\n1. Numbered one\n2. Numbered two"
        html = _markdown_to_html(md)
        assert "<ul>" in html
        assert "</ul>" in html
        assert "<ol>" in html
        assert "</ol>" in html
        assert html.index("<ul>") < html.index("<ol>")

    def test_mixed_ordered_then_unordered(self):
        md = "1. First\n2. Second\n- Bullet"
        html = _markdown_to_html(md)
        assert "<ol>" in html
        assert "<ul>" in html
        assert html.index("<ol>") < html.index("<ul>")

    # ------------------------------------------------------------------
    # Paragraphs and blank lines
    # ------------------------------------------------------------------

    def test_plain_paragraph(self):
        html = _markdown_to_html("This is a paragraph.")
        assert "<p>This is a paragraph.</p>" in html

    def test_blank_line_closes_list(self):
        md = "- Item\n\nParagraph after"
        html = _markdown_to_html(md)
        ul_close = html.index("</ul>")
        p_open = html.index("<p>")
        assert ul_close < p_open

    def test_empty_string_produces_empty_output(self):
        assert _markdown_to_html("") == ""

    # ------------------------------------------------------------------
    # HTML escaping
    # ------------------------------------------------------------------

    def test_html_chars_are_escaped(self):
        html = _markdown_to_html("Result: x < y & z > 0")
        assert "<" not in html.replace("<p>", "").replace("</p>", "")
        assert "&lt;" in html
        assert "&amp;" in html

    def test_heading_content_escaped(self):
        html = _markdown_to_html("# Title <script>alert(1)</script>")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    # ------------------------------------------------------------------
    # Full report-style document
    # ------------------------------------------------------------------

    def test_realistic_report(self):
        md = (
            "# Automation Report\n\n"
            "## Result\n"
            "Task succeeded.\n\n"
            "## Steps Taken\n"
            "1. Navigated to example.com\n"
            "2. Extracted page content\n\n"
            "## Issues\n"
            "- Minor: cookie banner dismissed\n"
        )
        html = _markdown_to_html(md)
        assert "<h1>Automation Report</h1>" in html
        assert "<h2>Result</h2>" in html
        assert "<ol>" in html
        assert "<ul>" in html
        assert "<li>Navigated to example.com</li>" in html
        assert "<li>Minor: cookie banner dismissed</li>" in html
