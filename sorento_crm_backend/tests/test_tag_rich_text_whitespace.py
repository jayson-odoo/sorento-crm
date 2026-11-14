"""PRICETAG-DESIGNER-FEEDBACK AC-2.6: the tag rich-text sanitiser keeps a description's indent.

UAC: documentation/plans/dealer-kit/pricetag-designer-feedback-acceptance-criteria.md, AC-2.6.
Owner, 14 Nov: "   L580xW450xH450mm" under "Basin size:" lost its leading spaces. The editor may
send the indent as plain spaces or as `&nbsp;`; a save round trip through `sanitise_tag_html`
must keep either form (a non-breaking space may come back as `&nbsp;`, `&#160;` or U+00A0).

Pure unit tests, no database.
"""
from __future__ import annotations

import pytest

from app.utils.tag_rich_text import sanitise_tag_html

_NBSP_FORMS = ("&nbsp;", "&#160;", "&#xa0;", " ")


def _spaced(value: str | None) -> str:
    """Every non-breaking-space form read as one plain space."""
    out = value or ""
    for form in _NBSP_FORMS:
        out = out.replace(form, " ")
    return out


def test_ac_2_6_leading_spaces_in_a_paragraph_survive():
    html = "<p>Basin size:</p><p>   L580xW450xH450mm</p>"
    assert sanitise_tag_html(html) == html


def test_ac_2_6_repeated_spaces_between_words_survive():
    html = "<p>Basin   size:   L580</p>"
    assert sanitise_tag_html(html) == html


def test_ac_2_6_leading_spaces_after_a_line_break_survive():
    out = sanitise_tag_html("<p>Basin size:<br>   L580xW450xH450mm</p>")
    assert out is not None
    assert out.replace("<br />", "<br>").replace("<br/>", "<br>") == "<p>Basin size:<br>   L580xW450xH450mm</p>"


@pytest.mark.parametrize("nbsp", ["&nbsp;", "&#160;", " "])
def test_ac_2_6_nbsp_indent_survives(nbsp: str):
    out = sanitise_tag_html(f"<p>Basin size:</p><p>{nbsp * 3}L580xW450xH450mm</p>")
    assert out is not None
    # Still non-breaking: the indent is not collapsed to ordinary spaces or dropped.
    assert any(form in out for form in _NBSP_FORMS)
    assert _spaced(out) == "<p>Basin size:</p><p>   L580xW450xH450mm</p>"


def test_ac_2_6_round_trip_is_stable():
    html = "<p>Basin size:</p><p>&nbsp;&nbsp;&nbsp;L580xW450xH450mm</p><p>   W450</p>"
    once = sanitise_tag_html(html)
    assert once is not None
    assert sanitise_tag_html(once) == once
    assert "   W450" in once
    assert "   L580xW450xH450mm" in _spaced(once)
