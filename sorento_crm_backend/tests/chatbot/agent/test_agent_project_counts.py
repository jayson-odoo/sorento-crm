"""AGENT-PROJECT-SCOPE crew browser pass on b9852915 (11 Nov): two answers that misled.

1. A salesperson with no projects read "You currently do not own any projects in the CRM ((not verified)
   projects found)": an EMPTY result did not back 0, and the repair wrote "(not verified)" into the sentence.
   An empty result backs 0, and a repair never writes into a sentence: it leaves the sentence out and says so.
2. "How many projects and who owns them" answered the right total (16) but "A: 10, B: 6" against 8 / 8: the
   model counted the rows itself (16 full rows do not fit the result cap). `crm_projects_list` now carries
   `count_by_owner` computed from every row before the cap, and the number check holds a figure written beside
   an owner's name to that owner's count. Pure unit tests, no DB, no LLM. Every name is fictional.
"""
from __future__ import annotations

import pytest

from app.services.chatbot.agent import tools as agent_tools
from app.services.chatbot.agent.loop import NOT_VERIFIED, final_reply, verify_answer

LIST = "crm_projects_list"
ALI, SITI = "ZZT Ali Owner", "ZZT Siti Owner"


def _check(text: str, ledger: dict, user_text: str = "how many projects do I own"):
    bad, _ = verify_answer({"text": text}, ledger, user_text)
    reply, _ = final_reply({"text": text}, bad, [], ledger=ledger)
    return bad, reply


# --- 1. an empty result backs 0, and the repair never writes into a sentence ----------------------
def _empty_ledger() -> dict:
    return {"c1": {"name": LIST, "args": {"owner_user_ids": "me"}, "status": "empty",
                   "data": {"applied_filters": {"owner_user_ids": ["x"]}}}}


def test_an_empty_result_backs_zero():
    bad, reply = _check("You currently do not own any projects in the CRM (0 projects found).", _empty_ledger())
    assert bad == []
    assert reply == "You currently do not own any projects in the CRM (0 projects found)."


def test_an_empty_result_backs_nothing_but_zero():
    bad, _ = _check("You own 3 projects.", _empty_ledger())
    assert bad == ["3"]


def test_the_repair_leaves_the_sentence_out_and_never_writes_into_one():
    ledger = {"c1": {"name": LIST, "args": {}, "status": "ok", "data": {"data": [{"title": "x", "total": 4}]}}}
    text = "You own 4 projects. Your best one has 99 units. Ask me for details."
    bad, reply = _check(text, ledger)
    assert bad == ["99 units"]
    assert NOT_VERIFIED not in reply
    assert "99" not in reply
    assert reply.startswith("You own 4 projects. Ask me for details.")
    assert "could not check" in reply  # one closing note, outside every sentence


def test_a_line_of_a_list_with_a_bad_figure_is_left_out_whole():
    ledger = {"c1": {"name": LIST, "args": {}, "status": "ok", "data": {"total": 2}}}
    bad, reply = _check("Projects by owner:\n- Ali: 2\n- Siti: 7", ledger)
    assert bad == ["7"]
    assert "- Ali: 2" in reply and "Siti" not in reply and NOT_VERIFIED not in reply


# --- 2. per-owner counts come from the tool, and a figure beside an owner is held to it -----------
def _rows(owners: list[str]) -> list[dict]:
    return [{"id": f"p{i}", "title": f"ZZT Project {i}", "owner_name": o} for i, o in enumerate(owners)]


def test_count_by_owner_is_added_from_every_row():
    body = {"data": _rows([ALI] * 8 + [SITI] * 8), "pagination": {"total": 16}}
    out = agent_tools.with_owner_counts(LIST, body)
    assert out["count_by_owner"] == [{"owner": ALI, "projects": 8}, {"owner": SITI, "projects": 8}]


def test_count_by_owner_names_projects_with_no_owner():
    out = agent_tools.with_owner_counts(LIST, {"data": _rows([ALI, None]), "pagination": {"total": 2}})
    assert {"owner": "No owner", "projects": 1} in out["count_by_owner"]


def test_no_count_by_owner_when_the_page_does_not_hold_every_row():
    out = agent_tools.with_owner_counts(LIST, {"data": _rows([ALI] * 5), "pagination": {"total": 16}})
    assert "count_by_owner" not in out
    assert "16" in out["count_by_owner_note"]


def test_other_tools_are_untouched():
    body = {"data": _rows([ALI]), "pagination": {"total": 1}}
    assert agent_tools.with_owner_counts("crm_complaints_list", body) == body


def test_the_counts_survive_the_result_cap():
    """16 full rows are cut by the cap; the counts are computed before it and kept."""
    rows = [{**r, "notes": "x" * 2000} for r in _rows([ALI] * 8 + [SITI] * 8)]
    out = agent_tools.with_owner_counts(LIST, {"data": rows, "pagination": {"total": 16}})
    capped, more = agent_tools.cap_result(out)
    assert more > 0
    assert capped["count_by_owner"] == [{"owner": ALI, "projects": 8}, {"owner": SITI, "projects": 8}]


def _counts_ledger() -> dict:
    data = {"data": _rows([ALI] * 3), "pagination": {"total": 16},
            "count_by_owner": [{"owner": ALI, "projects": 8}, {"owner": SITI, "projects": 8}]}
    # `days_since_last_activity` 10 / 6: numbers elsewhere in the result must not back a per-owner count.
    data["data"][0]["days_since_last_activity"] = 10
    data["data"][1]["days_since_last_activity"] = 6
    return {"c1": {"name": LIST, "args": {}, "status": "ok", "data": data}}


def test_a_wrong_per_owner_count_is_caught_although_the_number_appears_elsewhere():
    bad, reply = _check(f"There are 16 projects. {ALI}: 10, {SITI}: 6.", _counts_ledger(), "who owns them")
    assert set(bad) == {"10", "6"}
    assert "16 projects" in reply and "10" not in reply


def test_the_right_per_owner_counts_pass():
    bad, reply = _check(f"There are 16 projects: {ALI} owns 8 and {SITI} owns 8.", _counts_ledger(), "who owns them")
    assert bad == []
    assert reply == f"There are 16 projects: {ALI} owns 8 and {SITI} owns 8."


@pytest.mark.parametrize("line", [f"- {ALI} (8 projects)", f"| {ALI} | 8 |", f"{ALI.lower()}: 8"])
def test_per_owner_counts_in_lists_and_tables(line):
    bad, _ = _check(f"Owners:\n{line}", _counts_ledger(), "who owns them")
    assert bad == []


def test_when_every_sentence_is_left_out_the_reply_says_what_happened_and_what_to_do():
    from app.services.chatbot.agent.loop import ALL_LEFT_OUT_NOTE, _redact_written

    assert _redact_written("You own 99 projects.", {"99"}) == ALL_LEFT_OUT_NOTE
    assert "again" in ALL_LEFT_OUT_NOTE
