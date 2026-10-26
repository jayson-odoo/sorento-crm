"""PROMPT-RULES-DIET red tests: `app/services/chatbot_prompt_diet_edits.py` (pure, no database).

Contract: PLAN-prompt-rules-diet-26oct.md. `EDITS: tuple[Edit, ...]` (Edit from chatbot_lookup_edits), applied to the
list-free text (a line equal to MARKER). Generic over EDITS: the fixture holds each text edit's own anchor once.
"""
from __future__ import annotations

import re

import pytest

from app.services import chatbot_lookup_edits as lle
from app.services import chatbot_prompt_diet_edits as diet
from tests.chatbot.test_prompt_lookup_edits import SALES_TARGET_SECTION

MARKER = "== LOOKUP LISTS =="
SALES_REPORT_ANCHOR = '== SALES REPORT: order_status "sales_report", domain_hint "order" =='
FILLER = "Filler rule one for {{current_date}}.\nFiller rule two stays."
HEADING = re.compile(r"^== .+ ==", re.M)
HEADING_INLINE = re.compile(r"== [^=\n]+? ==")

TEXT_EDITS = tuple(e for e in diet.EDITS if e.op != "replace_line")


@pytest.fixture(autouse=True)
def _text_edits_only(monkeypatch):
    monkeypatch.setattr(diet, "EDITS", TEXT_EDITS)


def fixture(*, skip: int | None = None, double: int | None = None, section: str = "") -> str:
    parts = [FILLER]
    for i, e in enumerate(TEXT_EDITS):
        if i != skip:
            parts.append(e.anchor)
        if i == double:
            parts.append(e.anchor)
    return "\n\n".join(parts) + "\n\n" + section + SALES_REPORT_ANCHOR + "\nSales report rules.\n" + MARKER + "\n"


def test_edits_non_empty():
    assert len(TEXT_EDITS) >= 1


def test_apply_removes_anchors_lands_payloads_keeps_filler_and_marker_last():
    out = diet.apply(fixture())
    assert out is not None
    for e in TEXT_EDITS:
        assert e.anchor not in out or e.payload.startswith(e.anchor), e.anchor[:60]
        if e.payload:
            assert e.payload in out, e.payload[:60]
    assert FILLER in out
    lines = out.rstrip("\n").splitlines()
    assert lines[-1] == MARKER
    assert sum(1 for ln in out.splitlines() if ln.strip() == MARKER) == 1


def _indices():
    n = len(TEXT_EDITS)
    return sorted({0, n - 1}) if n else []


@pytest.mark.parametrize("i", _indices())
def test_missing_anchor_gives_none(i):
    if len(TEXT_EDITS) < 2:
        pytest.skip("under 2 text edits")
    assert diet.apply(fixture(skip=i)) is None


@pytest.mark.parametrize("i", _indices())
def test_doubled_anchor_gives_none(i):
    if len(TEXT_EDITS) < 2:
        pytest.skip("under 2 text edits")
    assert diet.apply(fixture(double=i)) is None


def test_second_apply_is_none():
    once = diet.apply(fixture())
    assert once is not None and diet.apply(once) is None


def test_text_without_the_marker_line_gives_none():
    text = fixture().replace(MARKER + "\n", "")
    assert diet.apply(text) is None


def test_sales_target_section_coexists_byte_for_byte():
    out = diet.apply(fixture(section=SALES_TARGET_SECTION))
    assert out is not None
    assert SALES_TARGET_SECTION + SALES_REPORT_ANCHOR in out
    assert out.count(SALES_REPORT_ANCHOR) == 1


def test_data_invariants_over_edits():
    assert len(TEXT_EDITS) >= 1
    forbidden = ("<<<CHATBOT POLICY BLOCKS>>>", "<<<END CHATBOT POLICY BLOCKS>>>", "{{", "}}", MARKER, SALES_REPORT_ANCHOR)
    for e in TEXT_EDITS:
        for bad in forbidden:
            assert bad not in e.anchor, (bad, e.anchor[:60])
            assert bad not in e.payload, (bad, e.payload[:60])
        assert len(e.payload) < len(e.anchor), e.anchor[:60]
        a, p = set(HEADING_INLINE.findall(e.anchor)), set(HEADING_INLINE.findall(e.payload))
        assert a <= p, f"heading lost: {a - p}"
        assert p <= a, f"new section added: {p - a}"


def test_size_target_ac1():
    saved = sum(len(e.anchor) - len(e.payload) for e in TEXT_EDITS)
    assert diet.BASE_CHARS == 129_651 and diet.TARGET_CHARS == 90_000
    assert diet.BASE_CHARS - saved < diet.TARGET_CHARS, f"{diet.BASE_CHARS - saved} chars, target {diet.TARGET_CHARS}"


def test_build_runs_lookup_apply_only_without_the_marker(monkeypatch):
    calls = []

    def stub(text):
        calls.append(text)
        return fixture()

    monkeypatch.setattr(lle, "apply", stub)
    out = diet.build("plain production text")
    assert calls == ["plain production text"] and out == diet.apply(fixture())
    assert out is not None

    calls.clear()
    assert diet.build(fixture()) == diet.apply(fixture())
    assert calls == []

    monkeypatch.setattr(lle, "apply", lambda t: None)
    assert diet.build("plain production text") is None
