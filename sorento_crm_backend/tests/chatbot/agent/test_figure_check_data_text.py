"""Figure check leaves data text alone (F1) and accepts rounded figures (F2).

Plan: documentation/plans/chatbot/PLAN-agentic-unify-tools-1nov.md, section
"Fix round after crew's browser pass, 2 Nov". Pure unit tests, no DB, no LLM.

`final_reply` needs this turn's ledger to know which spans are data text; the redaction tests pass it
as `ledger=` via `_check_with_ledger` (the plan fixes the rule, not the keyword; the coder may rename
it there, in one place).
"""
from __future__ import annotations

import pytest

from app.services.chatbot.agent.loop import final_reply, verify_answer

TITLE = "ZZT browser 1613 recheck"
UUID = "8f14e45f-ceea-4d67-9f5e-0a1b2c3d4e5f"


def _ledger(data) -> dict:
    return {"c1": {"name": "crm_projects_list", "args": {}, "status": "ok", "data": data}}


def _projects(key: str = "title", value: str = TITLE) -> dict:
    return {"data": [{"id": UUID, key: value, "status": "Active"}]}


def _check(text: str, data, user_text: str = "show it"):
    """(unbacked numbers, redacted reply). The reply uses today's final_reply signature."""
    ledger = _ledger(data)
    bad, _ = verify_answer({"text": text}, ledger, user_text)
    reply, _ = final_reply({"text": text}, bad, [])
    return bad, reply


def _check_with_ledger(text: str, data):
    """As _check, but final_reply is handed the ledger (needed to know which spans are data text)."""
    ledger = _ledger(data)
    bad, _ = verify_answer({"text": text}, ledger, "show it")
    reply, _ = final_reply({"text": text}, bad, [], ledger=ledger)
    return bad, reply


def test_title_digits_in_text_are_not_reported_or_redacted():
    """F1: the title repeated verbatim is data text."""
    bad, reply = _check_with_ledger(f"The project is {TITLE}.", _projects())
    assert bad == []
    assert TITLE in reply and "(not verified)" not in reply


def test_title_in_other_letter_case_is_still_data_text():
    """F1: letter case does not matter."""
    bad, reply = _check_with_ledger("The project is zzt browser 1613 recheck.", _projects())
    assert bad == []
    assert "zzt browser 1613 recheck" in reply and "(not verified)" not in reply


def test_name_key_value_is_data_text_too():
    """F1: the key `name` is covered the same way."""
    bad, reply = _check_with_ledger("It is ZZT browser 1613 recheck.", _projects("name"))
    assert bad == []
    assert TITLE in reply and "(not verified)" not in reply


def test_standalone_figure_is_still_reported_and_only_it_is_redacted():
    """F1: a bad 1613 elsewhere is reported and redacted, the title's 1613 is kept."""
    bad, reply = _check_with_ledger(f"{TITLE} has 1613 units.", _projects())
    assert bad == ["1613 units"]  # `_figures` writes the figure with its unit word
    assert TITLE in reply
    assert reply.count("(not verified)") == 1
    assert "1613 units" not in reply


def test_name_like_value_still_never_backs_a_figure_elsewhere():
    """F1 key rule stays: {"name": "Basin 600"} does not back "600 units"."""
    data = {"data": [{"name": "Basin 600"}]}
    bad, reply = _check("There are 600 units.", data)
    assert bad == ["600 units"]
    assert "600 units" not in reply and "(not verified)" in reply


def test_string_without_a_letter_is_a_plain_figure_source():
    """F1: "1613" under a non-name key backs "1613" as today."""
    bad, _ = _check("There are 1613 units.", {"data": [{"code": "1613"}]})
    assert bad == []


def test_string_with_letters_but_no_digit_protects_nothing():
    """F1: a value with no digit protects no digits (no change)."""
    bad, _ = _check("There are 1613 units.", {"data": [{"title": "Basin recheck"}]})
    assert bad == ["1613 units"]


SLA = {"average_response_time": 3.456789, "average_resolution_time": 26.04166,
       "escalation_rate": 12.345678, "total_trackings": 81}


@pytest.mark.parametrize("text", [
    "3.46 hours", "3.5 hours", "3 hours", "26.04 hours", "26 hours", "12.3%", "12%", "81 trackings",
])
def test_rounded_figure_is_backed(text):
    """F2: a source rounded half up to the written decimals backs the figure."""
    bad, reply = _check(f"It took {text}.", SLA)
    assert bad == []
    assert "(not verified)" not in reply


@pytest.mark.parametrize("text,written", [
    ("3.45 hours", "3.45"), ("3.47 hours", "3.47"), ("4 hours", "4"), ("12.4%", "12.4%"),
])
def test_wrongly_rounded_figure_is_reported_and_redacted(text, written):
    """F2: 3.456789 never backs 3.45, 3.47 or 4; 12.345678 never backs 12.4."""
    bad, reply = _check(f"It took {text}.", SLA)
    assert bad == [written]
    assert "(not verified)" in reply


def test_whole_source_never_backs_extra_precision():
    """F2: a whole 12 does not back 12.3."""
    bad, _ = _check("There are 12.3 of them.", {"count": 12})
    assert bad == ["12.3"]


def test_rounding_is_half_up():
    """F2: 2.25 backs 2.3, not 2.2."""
    assert _check("It is 2.3.", {"value": 2.25})[0] == []
    assert _check("It is 2.2.", {"value": 2.25})[0] == ["2.2"]


def test_column_total_is_rounded_too():
    """F2: rows 1.004 + 2.003 total 3.007: backs 3.01 and 3, not 3.00 or 3.1."""
    data = {"data": [{"amount": 1.004}, {"amount": 2.003}]}
    assert _check("Total 3.01.", data)[0] == []
    assert _check("Total 3.", data)[0] == []
    assert _check("Total 3.00.", data)[0] == ["3.00"]
    assert _check("Total 3.0.", data)[0] == ["3.0"]


def test_users_own_figure_stays_exact():
    """F2: the user's 3.456789 does not back a rounded 3.46."""
    bad, _ = verify_answer({"text": "It is 3.46."}, _ledger({"data": []}), "is it 3.456789?")
    assert bad == ["3.46"]
