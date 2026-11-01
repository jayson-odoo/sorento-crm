"""Rich-text letter and terms reduced for the quotation PDF: bold kept, clauses numbered once.

Pure functions, no database. The clause wording is invented.
"""
from types import SimpleNamespace

from app.services import project_quotation_pdf_service as pdf


def test_bold_survives_as_strong():
    blocks = pdf._text_blocks("<p>Pay <strong>within 30 days</strong> of invoice</p>")
    assert blocks == ["Pay <strong>within 30 days</strong> of invoice"]


def test_b_tag_is_normalised_and_other_markup_is_dropped():
    blocks = pdf._text_blocks('<p><b>Note</b> <em>this</em> <script>x</script></p>')
    assert blocks == ["<strong>Note</strong> this x"]


def test_markup_in_text_is_escaped():
    blocks = pdf._text_blocks("<p>Sample &lt;img src=x&gt; clause</p>")
    assert blocks == ["Sample &lt;img src=x&gt; clause"]


def test_bold_spanning_two_blocks_is_balanced_in_each():
    blocks = pdf._text_blocks("<p><strong>First</p><p>Second</strong> plain</p>")
    assert blocks == ["<strong>First</strong>", "<strong>Second</strong> plain"]


def test_ordered_list_prints_numbered_exactly_once():
    issue = SimpleNamespace(
        terms_rendered="<ol><li><p>Sample clause alpha</p></li><li><p>Sample clause beta</p></li></ol>"
    )
    html = pdf._terms_html(issue)
    assert html.count("<ol>") == 1
    assert html.count("<li>") == 2
    assert "<li>Sample clause alpha</li><li>Sample clause beta</li>" in html


def test_typed_numbers_are_not_printed_twice():
    issue = SimpleNamespace(
        terms_rendered="<ol><li>1. Sample clause alpha</li><li>2) Sample clause beta</li></ol>"
    )
    html = pdf._terms_html(issue)
    assert "<li>Sample clause alpha</li><li>Sample clause beta</li>" in html


def test_decimal_clause_reference_is_kept():
    issue = SimpleNamespace(terms_rendered="<ol><li>1.1 Sample sub clause</li></ol>")
    assert "<li>1.1 Sample sub clause</li>" in pdf._terms_html(issue)


def test_letter_keeps_typed_numbers():
    assert pdf._text_blocks("<p>2. Sample paragraph</p>") == ["2. Sample paragraph"]


def test_empty_terms_render_nothing():
    assert pdf._terms_html(SimpleNamespace(terms_rendered=None)) == ""
