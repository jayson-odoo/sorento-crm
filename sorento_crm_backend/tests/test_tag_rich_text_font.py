"""PRICETAG-DESIGNER-FEEDBACK B1, AC-1.5: the sanitiser keeps a per-word font.

UAC: documentation/plans/dealer-kit/pricetag-designer-feedback-b-acceptance-criteria.md AC-1.5.

`app/utils/tag_rich_text.py` keeps `font-family` (a plain family name: letters, digits, spaces,
hyphens, optional quotes; nothing else) and `font-size` (number + pt, 4 to 200) on a span. Any
other value in those properties is dropped. Written test-FIRST; pure unit tests, no database.
"""
from __future__ import annotations

import pytest

from app.utils.tag_rich_text import sanitise_tag_html


def _span_style(html: str | None) -> str:
    """The style attribute of the first span in sanitised output, or '' when there is none."""
    assert html is not None
    marker = '<span style="'
    at = html.find(marker)
    if at < 0:
        return ""
    end = html.find('">', at + len(marker))
    return html[at + len(marker):end]


def test_keeps_font_family_and_size_on_span():
    out = sanitise_tag_html('<p>A <span style="font-family: Montserrat; font-size: 14pt">B</span></p>')
    assert out == '<p>A <span style="font-family: Montserrat; font-size: 14pt">B</span></p>'


def test_keeps_family_with_digits_spaces_and_hyphens():
    out = sanitise_tag_html('<p><span style="font-family: Open Sans-2 Condensed">B</span></p>')
    assert "font-family: Open Sans-2 Condensed" in _span_style(out)


@pytest.mark.parametrize("family", ["'Bebas Neue'", '&quot;Bebas Neue&quot;'])
def test_keeps_a_quoted_family(family: str):
    out = sanitise_tag_html(f'<p><span style="font-family: {family}">B</span></p>')
    style = _span_style(out)
    assert "font-family" in style
    assert "Bebas Neue" in style
    # The kept value can never break out of the style attribute.
    assert out is not None and out.count('"') == 2


def test_font_family_with_colour_keeps_both():
    out = sanitise_tag_html('<p><span style="color: #ff0000; font-family: Jost">B</span></p>')
    style = _span_style(out)
    assert "color: #ff0000" in style
    assert "font-family: Jost" in style


@pytest.mark.parametrize(
    "family",
    [
        "url(https://evil.test/x.woff)",
        "expression(alert(1))",
        "Arial, sans-serif",
        "Comic<Sans",
        "Arial\\3b color",
        "Arial/*x*/",
    ],
)
def test_drops_a_family_that_is_not_a_plain_name(family: str):
    out = sanitise_tag_html(f'<p><span style="font-family: {family}">B</span></p>')
    assert out is not None
    assert "font-family" not in out
    assert "url(" not in out
    assert "expression" not in out
    assert "B" in out


def test_injected_semicolon_keeps_only_the_plain_family():
    out = sanitise_tag_html(
        '<p><span style="font-family: Arial;background: url(javascript:alert(1))">B</span></p>'
    )
    assert out is not None
    assert "font-family: Arial" in _span_style(out)
    assert "url(" not in out
    assert "javascript" not in out
    assert "background" not in out


@pytest.mark.parametrize("size", ["4pt", "14pt", "12.5pt", "200pt"])
def test_keeps_font_size_in_range(size: str):
    out = sanitise_tag_html(f'<p><span style="font-size: {size}">B</span></p>')
    assert f"font-size: {size}" in _span_style(out)


@pytest.mark.parametrize(
    "size",
    ["3pt", "201pt", "14px", "14", "1em", "-14pt", "14pt !important", "calc(14pt)", "expression(14)"],
)
def test_drops_a_font_size_that_is_not_pt_in_range(size: str):
    out = sanitise_tag_html(f'<p><span style="font-size: {size}">B</span></p>')
    assert out is not None
    assert "font-size" not in out
    assert "B" in out


def test_font_props_only_on_span_not_on_a_paragraph():
    out = sanitise_tag_html('<p style="font-family: Arial; font-size: 14pt">B</p>')
    assert out == "<p>B</p>"
