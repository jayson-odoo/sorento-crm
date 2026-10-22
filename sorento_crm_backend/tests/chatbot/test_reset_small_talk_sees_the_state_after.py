"""CHAT-PICK-QTY-STATE release gate (#1829), contact 04: the small-talk lane over a reset.

EVAL-BENCH replayed "clear all" over a stored session holding a one-option warehouse offer and a
parked twenty-line stock check. The turn was a reset and went to the small-talk (low_signal)
lane, but the lane's model prompt carried the session as it was BEFORE the turn, offer
included, and the reply claimed a warehouse check.

Crew ruling (crew-note 6333557214): on a reset turn the small-talk lane renders the state AFTER
the reset - no open question, offer, hand-over team, task or stored list in what its model
sees. Every other small-talk turn shows exactly what it showed before.

Driven through `engine.run_turn` with the session stored on the contact, the parser stubbed
with the v63 "clear all" read (topic_reset false, cancel, nothing named) on the old path and
the v92 read (the same, with `close_question`) on the state path, and the model call stubbed
(`conftest._stub_casual_llm` records what it is sent). Synthetic codes only.
"""
from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest
from sqlalchemy import text

from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import parser as parser_mod
from app.services.chatbot.turn import pending as turn_pending
from app.services.chatbot.turn.state import Focus, focus_to_wire
from tests.chatbot import _ht26_fixtures as ht
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output, stub_access  # noqa: F401

GATES = pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
TWENTY = [f"SRTZQ{i:03d}" for i in range(1, 21)]


def _stored_session() -> dict[str, Any]:
    offer = turn_pending.ask(
        "team_pick", [{"position": 1, "label": "Yes", "entity_type": "team", "payload": {}}],
        team="warehouse", asked_at_turn=1, expects="yes_no",
    )
    task = ht.stock_task([(c, None) for c in TWENTY], status="parked", opened_at_turn=0, touched_at_turn=0)
    focus = Focus(products=ht.product_rows(TWENTY[0]), domains=["inventory"], tasks=(task,))
    return {
        "focus": focus_to_wire(focus),
        "open_question": turn_pending.to_wire(offer),
        "ideation": None,
        "access_levels": [],
        "contains_flyer": False,
        "reply_language": None,
    }


def _seed(session_factory, session_vars: dict[str, Any]) -> None:
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": str(CONTACT_ID), "phone": "+60000000009", "sv": json.dumps(session_vars)},
    )
    db.commit()


def _stub_parser(monkeypatch, gate: bool, emission: dict[str, Any]) -> None:
    def fake_resolve_config(db, *, current_date, override_version_id=None):
        cfg = parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test"
        )
        return dataclasses.replace(cfg, state_block=True) if gate else cfg

    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: emission)


def _say(session_factory, monkeypatch, stub_access, gate, emission, words):  # noqa: F811
    _seed(session_factory, _stored_session())
    _stub_parser(monkeypatch, gate, emission)
    stub_access()
    env = _envelope()
    env.message["message"]["message"]["text"] = words
    return engine_mod.run_turn(env, session_factory=session_factory)


def _shown_session(prompt: str) -> dict[str, Any]:
    """The `session_vars:` line of the clarifier's user message (`casual.render_user_message`)."""
    line = next(row for row in prompt.splitlines() if row.startswith("session_vars: "))
    return json.loads(line[len("session_vars: "):].strip())


def _clear_all(gate: bool) -> dict[str, Any]:
    emission = _parser_output(
        intent_hint="check_stock" if gate else None, domain_hint="inventory" if gate else None,
        scope_intent=None, user_goal="clear all", match_mode=None, entities=[], entity_op="clear",
        broaden_axis="all", topic_reset=False, scope_exclusive=None, contains_flyer=None, correction=None,
        escalation={"is_escalation_confirmation": None, "company_pick": None},
        open_question_answer={"mode": "cancel", "picked": [], "items": [], "qty_for_all": None},
    )
    if gate:
        emission["state_changes"] = [{"op": "close_question", "axis": None, "position": None}]
    return emission


@GATES
def test_a_reset_small_talk_model_sees_no_offer_team_task_or_list(
    session_factory, monkeypatch, stub_access, _stub_casual_llm, gate  # noqa: F811
):
    result = _say(session_factory, monkeypatch, stub_access, gate, _clear_all(gate), "clear all")
    assert result.branch_kind == "low_signal", result.branch_kind
    assert _stub_casual_llm, "the small-talk model was not called"
    prompt = _stub_casual_llm[-1]["user_prompt"]
    shown = _shown_session(prompt)
    assert not shown.get("open_question"), shown.get("open_question")
    assert not (shown.get("focus") or {}).get("tasks"), (shown.get("focus") or {}).get("tasks")
    assert not (shown.get("focus") or {}).get("last_list"), (shown.get("focus") or {}).get("last_list")
    assert "variables" not in shown, shown.get("variables")
    for word in ("team_pick", "warehouse", "stock_qty"):
        assert word not in prompt, (word, prompt)


@GATES
def test_guard_small_talk_that_is_not_a_reset_still_sees_the_stored_session(
    session_factory, monkeypatch, stub_access, _stub_casual_llm, gate  # noqa: F811
):
    """A "thanks" over the open offer answers nothing and resets nothing: the model is shown the
    stored session exactly as before, offer and parked task included."""
    emission = _parser_output(
        message_type="confirmation", intent_hint=None, domain_hint=None, scope_intent=None, user_goal="thanks",
        match_mode=None, entities=[], entity_op=None, topic_reset=False, scope_exclusive=None,
        contains_flyer=None, correction=None, escalation={"is_escalation_confirmation": None, "company_pick": None},
        open_question_answer={"mode": None, "picked": [], "items": [], "qty_for_all": None},
    )
    if gate:
        emission["state_changes"] = []
    result = _say(session_factory, monkeypatch, stub_access, gate, emission, "thanks")
    assert result.branch_kind == "low_signal", result.branch_kind
    assert _stub_casual_llm, "the small-talk model was not called"
    assert _shown_session(_stub_casual_llm[-1]["user_prompt"]) == _stored_session()
