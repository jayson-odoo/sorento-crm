"""PRICETAG-COMBO-FORMAT S2: the server-side allow-list for stored tag HTML.

UAC: documentation/plans/dealer-kit/pricetag-combo-format-acceptance-criteria.md, AC-5 to AC-8,
AC-11, AC-12. Contract: pricetag-combo-format-contract.md (`app/utils/tag_rich_text.py`).

Written test-FIRST (PRINCIPLES.md Phase 2). `app/utils/tag_rich_text.py` does not exist yet, so
the module import below is the one red line for the whole file. Pure unit tests, no database.

Inputs that must go through the sanitiser start with an allowed BLOCK tag: a value that does not
(`is_rich` false) is legacy plain text and is returned unchanged by contract (AC-11), so a bare
`<script>x</script>` is NOT a sanitiser case.

KILL notes (the reviewer reverts the named line and the named tests must go red):
  * remove the attribute filter           -> test_attributes_are_all_dropped (4) goes red
  * remove the style-value regex          -> the colour tests (2) go red
  * remove the drop-with-content set      -> test_dangerous_elements_are_dropped_with_content (5)
"""
from __future__ import annotations

import pytest

# THE red import: the module does not exist until S2 lands.
from app.utils.tag_rich_text import is_rich, plain_text, sanitise_tag_html

from tests._tag_rich_fixture import E1_HTML, E1_LINES


def _br(value: str | None) -> str | None:
    """`<br>` may be serialised `<br>` or `<br/>`; the contract does not pin it."""
    if value is None:
        return None
    return value.replace("<br />", "<br>").replace("<br/>", "<br>")


# --------------------------------------------------------------------------- AC-5
@pytest.mark.parametrize(
    "html",
    [
        "<p>x</p>",
        "<h1>x</h1>",
        "<h2>x</h2>",
        "<h3>x</h3>",
        "<blockquote>x</blockquote>",
        "<ul><li>x</li></ul>",
        "<ol><li>x</li></ol>",
        "<p><strong>x</strong></p>",
        "<p><em>x</em></p>",
        "<p><s>x</s></p>",
        "<p><u>x</u></p>",
        "<p><code>x</code></p>",
        "<p><a>x</a></p>",
        "<p><span>x</span></p>",
        "<p><mark>x</mark></p>",
        "<p>a<br>b</p>",
    ],
)
def test_every_allowed_element_is_kept_with_its_text(html):
    """AC-5: `p br strong em s u code h1 h2 h3 ul ol li blockquote a span mark` survive."""
    assert _br(sanitise_tag_html(html)) == html


# --------------------------------------------------------------------------- AC-6
@pytest.mark.parametrize(
    "value",
    ["#6b7280", "#abc", "rgb(1, 2, 3)", "#ABCDEF"],
)
def test_a_valid_colour_is_kept(value):
    """AC-6: `#rgb`, `#rrggbb` and `rgb(r, g, b)` on a span; re-emitted lower-case."""
    out = sanitise_tag_html(f'<p><span style="color: {value}">x</span></p>')
    assert out == f'<p><span style="color: {value.lower()}">x</span></p>'


@pytest.mark.parametrize(
    "value",
    [
        "red",
        "#12345g",
        "rgb(1,2)",
        "url(javascript:alert(1))",
        "expression(x)",
        "#12",
        "#1234567",
    ],
)
def test_an_invalid_colour_drops_the_style_and_keeps_the_text(value):
    """AC-6: any other colour value removes the declaration, so the empty style attribute
    goes with it. KILL: remove the style-value regex."""
    out = sanitise_tag_html(f'<p><span style="color: {value}">x</span></p>')
    assert out == "<p><span>x</span></p>"


def test_background_colour_follows_the_same_rules_on_span_and_mark():
    assert (
        sanitise_tag_html('<p><span style="background-color: #fde68a">x</span></p>')
        == '<p><span style="background-color: #fde68a">x</span></p>'
    )
    assert (
        sanitise_tag_html('<p><mark style="background-color: #fde68a">x</mark></p>')
        == '<p><mark style="background-color: #fde68a">x</mark></p>'
    )
    assert sanitise_tag_html('<p><mark style="background-color: red">x</mark></p>') == "<p><mark>x</mark></p>"
    assert (
        sanitise_tag_html('<p><span style="background-color: url(x)">x</span></p>')
        == "<p><span>x</span></p>"
    )


def test_text_align_is_kept_on_block_tags_only():
    for tag in ("p", "h1", "h2", "h3"):
        for side in ("left", "center", "right"):
            html = f'<{tag} style="text-align: {side}">x</{tag}>'
            assert sanitise_tag_html(html) == html, (tag, side)
    li = '<ul><li style="text-align: center">x</li></ul>'
    assert sanitise_tag_html(li) == li
    # not on a span
    assert (
        sanitise_tag_html('<p><span style="text-align: center">x</span></p>')
        == "<p><span>x</span></p>"
    )
    # an unknown alignment is removed
    assert sanitise_tag_html('<p style="text-align: justify">x</p>') == "<p>x</p>"


def test_colour_is_not_kept_on_a_block_tag():
    """Contract: `color` / `background-color` are allowed on `span` and `mark` only."""
    assert sanitise_tag_html('<p style="color: #fff">x</p>') == "<p>x</p>"


@pytest.mark.parametrize(
    "declaration",
    ["font-size: 40px", "position: fixed", "font-family: Comic Sans", "display: none"],
)
def test_other_declarations_are_removed(declaration):
    out = sanitise_tag_html(f'<p><span style="{declaration}">x</span></p>')
    assert out == "<p><span>x</span></p>"


def test_kept_declarations_are_joined_and_the_rest_dropped():
    out = sanitise_tag_html(
        '<p><span style="COLOR: #FFF; font-size: 99px; background-color: #000">x</span></p>'
    )
    assert out == '<p><span style="color: #fff; background-color: #000">x</span></p>'


@pytest.mark.parametrize(
    "attribute",
    ['href="http://x"', 'class="c"', 'id="i"', 'onclick="alert(1)"', 'onmouseover="y"',
     'data-x="1"', 'target="_blank"'],
)
def test_attributes_are_all_dropped(attribute):
    """AC-6: every attribute but `style`, including on `a`. KILL: remove the attribute filter."""
    assert sanitise_tag_html(f"<p><a {attribute}>t</a></p>") == "<p><a>t</a></p>"
    assert sanitise_tag_html(f"<p {attribute}>t</p>") == "<p>t</p>"


# --------------------------------------------------------------------------- AC-7
@pytest.mark.parametrize("tag", ["script", "style", "iframe", "object", "embed"])
def test_dangerous_elements_are_dropped_with_content(tag):
    """AC-7. KILL: remove the content-drop set."""
    out = sanitise_tag_html(f"<p>a<{tag}>alert(1)</{tag}>x</p>")
    assert out == "<p>ax</p>"
    assert "alert" not in out


def test_unknown_tags_are_removed_and_their_text_kept():
    assert sanitise_tag_html("<p>a<img src=x onerror=alert(1)></p>") == "<p>a</p>"
    assert sanitise_tag_html("<p><div>a</div></p>") == "<p>a</p>"
    assert sanitise_tag_html("<p><svg><text>t</text></svg></p>") == "<p>t</p>"
    assert sanitise_tag_html("<p><table><tr><td>c</td></tr></table></p>") == "<p>c</p>"


# --------------------------------------------------------------------------- AC-8
def test_text_stays_escaped_and_never_becomes_a_tag():
    assert sanitise_tag_html("<p>&lt;b&gt;</p>") == "<p>&lt;b&gt;</p>"
    assert sanitise_tag_html("<p>a &amp; b</p>") == "<p>a &amp; b</p>"
    out = sanitise_tag_html("<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>")
    assert "<script" not in out


def test_comments_and_doctype_are_dropped_and_unclosed_tags_closed():
    assert sanitise_tag_html("<p>a<!-- c -->b</p>") == "<p>ab</p>"
    assert sanitise_tag_html("<p>a<!DOCTYPE html>b</p>") == "<p>ab</p>"
    assert sanitise_tag_html("<p><strong>a") == "<p><strong>a</strong></p>"


_CORPUS = [
    "<p>x</p>",
    "<p><strong>a</strong> (b)</p>",
    '<p><span style="color: #6b7280">x</span></p>',
    '<p><span style="color: red">x</span></p>',
    '<p style="text-align: center">x</p>',
    '<p style="text-align: justify">x</p>',
    "<p>a<img src=x onerror=alert(1)></p>",
    "<p>a<script>alert(1)</script>b</p>",
    "<p>&lt;b&gt;</p>",
    "<p>a &amp; b</p>",
    "<p>a<!-- c -->b</p>",
    "<p><strong>unclosed",
    "<ul><li>a</li><li>b<ul><li>c</li></ul></li></ul>",
    "<ol><li>a</li></ol><ol><li>b</li></ol>",
    "<h1>T</h1><h2>U</h2><h3>V</h3>",
    "<blockquote>q</blockquote>",
    '<p><a href="http://x" class="c" onclick="y">link</a></p>',
    '<p><mark style="background-color: #fde68a">m</mark></p>',
    "<p><div>a</div><svg><text>t</text></svg></p>",
    E1_HTML,
]


@pytest.mark.parametrize("html", _CORPUS)
def test_the_sanitiser_is_idempotent(html):
    """AC-8: sanitise(sanitise(x)) == sanitise(x)."""
    once = sanitise_tag_html(html)
    assert sanitise_tag_html(once) == once


def test_the_corpus_has_twenty_inputs():
    assert len(_CORPUS) >= 20


def test_e1_survives_the_sanitiser_unchanged():
    assert _br(sanitise_tag_html(E1_HTML)) == E1_HTML


def test_mixed_case_tags_and_attributes_are_handled_the_same():
    """AC-6, AC-7: `<SCRIPT>`, `ONERROR=`, `StYlE=`."""
    assert sanitise_tag_html("<p>a<SCRIPT>alert(1)</SCRIPT>b</p>") == "<p>ab</p>"
    assert sanitise_tag_html('<P ONCLICK="x">a</P>') == "<p>a</p>"
    assert sanitise_tag_html("<p>a<IMG SRC=x ONERROR=alert(1)></p>") == "<p>a</p>"
    assert (
        sanitise_tag_html('<p><SPAN StYlE="COLOR: #ABC">a</SPAN></p>')
        == '<p><span style="color: #abc">a</span></p>'
    )


# --------------------------------------------------------------------------- empty / AC-11
@pytest.mark.parametrize("value", [None, "", "   ", "\n\t "])
def test_nothing_is_stored_as_none(value):
    assert sanitise_tag_html(value) is None


@pytest.mark.parametrize("value", ["<p></p>", "<p> </p>", "<p><strong></strong></p>", "<p><br></p>"])
def test_markup_without_text_is_none(value):
    """AC-10 (unit half): no text content remains -> None."""
    assert sanitise_tag_html(value) is None


@pytest.mark.parametrize(
    "value, expected",
    [
        ("plain", False),
        ("SRTBF11416 (CABINET)\nL400xW345xH390mm", False),
        ("<p>x</p>", True),
        ("  <P>x", True),
        ("\n<h1>x", True),
        ("<h2 class=a>x", True),
        ("<h3>x", True),
        ("<ul><li>x", True),
        ("<ol>", True),
        ("<blockquote>x", True),
        ("<pre>x</pre>", False),
        ("<br>x", False),
        ("<span>x</span>", False),
        ("<b>x</b>", False),
        ("<h4>x</h4>", False),
        ("", False),
        (None, False),
    ],
)
def test_is_rich(value, expected):
    """AC-11: rich iff it starts with an allowed block tag followed by `>` or whitespace."""
    assert is_rich(value) is expected


def test_legacy_plain_text_is_returned_unchanged():
    """AC-11: plain text stays plain until it is edited in the editor."""
    legacy = "SRTBF11416 (CABINET)\nL400xW345xH390mm"
    assert sanitise_tag_html(legacy) == legacy
    assert sanitise_tag_html("a < b & c") == "a < b & c"
    assert sanitise_tag_html("<b>x</b>") == "<b>x</b>"


# --------------------------------------------------------------------------- AC-12
def test_plain_text_of_e1_is_its_lines_joined_by_newline():
    assert plain_text(E1_HTML) == "\n".join(E1_LINES)


def test_plain_text_of_lists():
    assert plain_text("<ul><li>a</li><li>b</li></ul>") == "• a\n• b"
    assert plain_text("<ol><li>a</li><li>b</li></ol><ol><li>c</li></ol>") == "1. a\n2. b\n1. c"
    assert plain_text("<ul><li>a<ul><li>b</li></ul></li></ul>") == "• a\n  • b"
    assert plain_text("<ol><li>a<ol><li>b</li></ol></li></ol>") == "1. a\n  1. b"


def test_plain_text_of_blocks_breaks_and_entities():
    assert plain_text("<h1>T</h1><p>x</p>") == "T\nx"
    assert plain_text("<p>a<br>b</p>") == "a\nb"
    assert plain_text("<p>a &amp; b &lt;c&gt;</p>") == "a & b <c>"
    assert "<" not in plain_text('<p><span style="color: #fff">x</span> <a>y</a></p>')


def test_plain_text_of_plain_input_is_unchanged_and_none_is_none():
    assert plain_text("a\nb") == "a\nb"
    assert plain_text("1 < 2 & 3") == "1 < 2 & 3"
    assert plain_text(None) is None
