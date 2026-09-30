"""The wide shell variant for table emails (EMAIL-HANDOVER-QTY, PR #1392, AC-8 to AC-10).

Owner (30 Sep): "this email template is too narrow already, the words are cramped". The
handover email's nine-column line table shared about 520px inside the 600px card with
40px side padding. A document may now say `width: "wide"`: 900px card, 24px side
padding, phone breakpoint at 920px. Everything else, and every document that does not
say so, renders exactly as before.

Pure rendering tests, no database - the same `_theme` / `_doc` shape
`tests/test_email_layout.py` uses.
"""
from __future__ import annotations

import re

import pytest

from app.services.email_layout import (
    EmailDocument,
    parse_document,
    plain_layout,
    render_document,
)

from .test_email_layout import CTX, FULL, _doc, _theme


def _render(doc=FULL, **kw):
    return render_document(doc, subject="Subj", context=CTX, theme=_theme(), **kw)


def _wide(*blocks):
    return EmailDocument.model_validate({"version": 1, "blocks": list(blocks), "width": "wide"})


WIDE = _wide(
    {"type": "brand_header"},
    {"type": "heading", "text": "Wide {{ who }}"},
    {"type": "custom_text", "html": "<table><tr><td>cell</td></tr></table>"},
    {"type": "button", "label": "Open it", "url": "{{ link }}"},
    {"type": "footer"},
)


# --- AC-8 the field --------------------------------------------------------------------
def test_document_width_defaults_to_standard():
    assert FULL.width == "standard"
    assert parse_document({"version": 1, "blocks": [{"type": "brand_header"}]}).width == "standard"
    assert parse_document({"version": 1, "blocks": [], "width": "wide"}).width == "wide"


def test_document_width_rejects_anything_else():
    with pytest.raises(ValueError):
        EmailDocument.model_validate({"version": 1, "blocks": [], "width": "huge"})


def test_document_width_round_trips_through_dump():
    assert WIDE.model_dump(mode="json")["width"] == "wide"
    assert FULL.model_dump(mode="json")["width"] == "standard"


# --- AC-9 the render ---------------------------------------------------------------------
def test_wide_document_renders_900_card_with_24px_gutters_and_920_breakpoint():
    html = _render(WIDE).body_html
    assert 'width="900"' in html and "max-width:900px" in html and "width:900px" in html
    assert 'width="600"' not in html and "max-width:600px" not in html
    assert "@media only screen and (max-width: 920px)" in html
    # Every content cell (heading, custom text, button, footer) sits on 24px gutters.
    pads = re.findall(r'class="em-pad"[^>]*style="(padding:[^;"]*)', html)
    assert pads, "no em-pad cells rendered"
    for pad in pads:
        assert " 40px" not in pad, pad
        assert "24px" in pad, pad
    # The brand band too.
    assert "padding:24px 24px;background-color:" in html


def test_standard_document_still_renders_exactly_the_600_shell():
    html = _render(FULL).body_html
    assert 'width="600"' in html and "max-width:600px" in html
    assert "@media only screen and (max-width: 620px)" in html
    assert 'width="900"' not in html
    pads = re.findall(r'class="em-pad"[^>]*style="(padding:[^;"]*)', html)
    assert pads and all("40px" in pad for pad in pads), pads


# --- AC-10 the fallback -----------------------------------------------------------------
def test_plain_safe_layout_stays_standard():
    out = plain_layout(subject="S", text="plain", theme=_theme())
    assert 'width="600"' in out.body_html and 'width="900"' not in out.body_html


def test_a_broken_wide_block_falls_back_to_the_standard_safe_layout(caplog):
    doc = _wide({"type": "brand_header"}, {"type": "heading", "text": "{{ who.bad( }}"}, {"type": "footer"})
    out = _render(doc)
    assert out.fallback_used
    assert 'width="600"' in out.body_html
