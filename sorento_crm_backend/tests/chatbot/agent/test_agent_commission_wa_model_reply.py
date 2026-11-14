"""AGENT-COMMISSION-WA, crew code gate on 2cfc3f83 (CP-3), owner ruling 14 Nov: the agent's reply text is the
model's only, no system-built or system-appended text (a structured card UI may stay). `_distance_reply` built the
next-tier reply in code and dropped or appended around the model's text. Now the tool returns the data (each row's
next-tier lines, the notes, the paging offset and how many more) with an instruction, and the reply is what the model
wrote.

The turn is played as the loop plays it: `run_query`, `query_result`, the ledger, `loop.final_reply`. No LLM.
"""
from __future__ import annotations

import inspect

import pytest

from tests.chatbot.agent.test_ai_tools_wave2 import grant, run, targets  # noqa: F401  (fixtures)
from tests.test_sales_targets_s1 import api, world  # noqa: F401  (fixtures)

ENTITY = "agent_target_summary"
OCT = "2026-10"


def _ledger(db, calls: list[dict]) -> dict:
    from app.services.chatbot.agent.query_tools import query_result

    ledger = {}
    for i, args in enumerate(calls):
        out = query_result(run(db, args), panel=True)
        ledger[f"q{i}"] = {"name": "crm_query", "status": out.status, "args": args, "data": out.data,
                           "display": out.display}
    return ledger


def _final(db, calls: list[dict], text: str) -> str:
    from app.services.chatbot.agent.loop import final_reply

    reply, _named = final_reply(
        {"text": text, "figures": [], "not_found": [], "not_checked": []}, [], [], ledger=_ledger(db, calls),
    )
    return reply


MODEL = (
    "Agent A is RM 1,000.00 away from tier 2 for 01/10/2026 - 31/10/2026.\n"
    "It would pay RM 300.00 there, RM 120.00 more than now."
)


@pytest.mark.parametrize("calls", [
    [{"entity": ENTITY, "agent": "Agent A", "period": OCT, "next_tier": "distance"}],
    [{"entity": ENTITY, "period": OCT, "next_tier": "closest", "subjects": "agent"}],
    [{"entity": ENTITY, "period": OCT, "next_tier": "closest", "subjects": "all"}],
    [{"entity": ENTITY, "agent": "Agent A", "period": OCT, "next_tier": "distance"},
     {"entity": ENTITY, "agent": "Agent B", "period": OCT, "next_tier": "distance"}],
], ids=["distance", "closest-agents", "closest-all", "two-subjects"])
def test_MR1_a_next_tier_reply_is_exactly_what_the_model_wrote(targets, calls):
    db, _c, _t = targets
    assert _final(db, calls, MODEL) == MODEL


def test_MR2_a_named_subject_not_found_is_still_only_the_models_text(targets):
    db, _c, _t = targets
    calls = [
        {"entity": ENTITY, "agent": "Nobody At All", "period": OCT, "next_tier": "distance"},
        {"entity": ENTITY, "agent": "Agent A", "period": OCT, "next_tier": "distance"},
    ]
    text = "I could not find Nobody At All.\nAgent A is RM 1,000.00 away from tier 2."
    assert _final(db, calls, text) == text


def test_MR3_no_note_is_appended_to_a_next_tier_reply(targets):
    """The notes are the model's to say (the instruction asks for them); code never adds them after its text."""
    db, _c, _t = targets
    calls = [{"entity": ENTITY, "period": OCT, "next_tier": "closest", "subjects": "dealer"}]
    data = _ledger(db, calls)["q0"]["data"]
    assert data.get("scope_note"), data  # there is a note to say
    assert _final(db, calls, "One short line.") == "One short line."


def test_MR4_the_model_gets_the_figures_not_a_card(targets):
    """The tool returns each row's next-tier lines (period as dd/mm/yyyy - dd/mm/yyyy) and the instruction; no
    code-rendered block stands in for the answer."""
    from app.services.chatbot.agent.query_tools import DISTANCE_INSTRUCTION, query_result

    db, _c, _t = targets
    out = query_result(run(db, {"entity": ENTITY, "agent": "Agent A", "period": OCT, "next_tier": "distance"}),
                       panel=True)
    assert out.display in (None, ""), out.display
    [row] = out.data["rows"]
    lines = row["next_tier_lines"]
    assert "tier 2" in lines and "to go, would pay" in lines and " - " in lines, lines
    assert out.data["instruction"] == DISTANCE_INSTRUCTION
    assert "Next tier:" not in (out.data.get("scope_note") or "")


def test_MR5_the_instruction_says_what_to_write():
    from app.services.chatbot.agent.query_tools import DISTANCE_INSTRUCTION

    said = DISTANCE_INSTRUCTION.lower()
    for must in ("next_tier_lines", "scope_note", "no markdown", "dd/mm/yyyy - dd/mm/yyyy", 'reply "more"',
                 "next_offset"):
        assert must in said, (must, DISTANCE_INSTRUCTION)


def test_MR6_a_cut_next_tier_page_tells_the_model_how_many_more_and_the_offset(targets, monkeypatch):
    from app.services.assistant_registry import sales
    from app.services.chatbot.agent.query_tools import query_result

    db, _c, _t = targets
    monkeypatch.setattr(sales, "NEXT_LINES", 1)
    out = query_result(run(db, {"entity": ENTITY, "period": OCT, "next_tier": "closest", "subjects": "all"}),
                       panel=True)
    assert len(out.data["rows"]) == 1 and out.data["truncated"] is True, out.data
    assert out.data["more"] == 1 and out.data["next_offset"] == 1


def test_MR7_no_code_builds_a_next_tier_reply():
    from app.services.chatbot.agent import loop, query_tools

    assert not hasattr(query_tools, "_distance_reply")
    assert "admitted" not in inspect.signature(query_tools.shape_reply).parameters
    assert "admitted" not in inspect.getsource(loop.final_reply)
