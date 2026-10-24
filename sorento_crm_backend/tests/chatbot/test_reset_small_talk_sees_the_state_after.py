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
    def fake_resolve_config(db, *, current_date, override_version_id=None, llm_choice=None):
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


ACK_EN = "Okay, I've cleared that. What would you like to check?"


def _saved_session(session_factory) -> dict[str, Any]:
    return session_factory().execute(
        text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :cid"), {"cid": str(CONTACT_ID)}
    ).scalar() or {}


def _assert_the_reset_keeps_nothing_open(session_factory, result, casual_calls) -> None:
    """Release gate #1829, round 8 ruling: a reset is the seam's turn, so no casual / clarifier
    model is called, the reply is the reset acknowledgement and nothing stays open."""
    assert not casual_calls, "a casual / clarifier model was called on a reset turn"
    assert (result.reply or {}).get("text") == ACK_EN, (result.branch_kind, (result.reply or {}).get("text"))
    saved = _saved_session(session_factory)
    assert saved.get("open_question") is None, saved.get("open_question")
    focus = saved.get("focus") or {}
    assert not focus.get("tasks"), focus.get("tasks")
    assert not focus.get("last_list"), focus.get("last_list")
    # The offer's kind and its hand-over team. (The focus wire always carries an empty
    # `"warehouse": []` location axis, so the bare word is no signal.)
    wire = json.dumps(saved, separators=(",", ":"))
    for word in ("team_pick", '"team":"warehouse"'):
        assert word not in wire, (word, wire)


@GATES
def test_a_reset_over_an_offer_calls_no_small_talk_model_and_keeps_nothing_open(
    session_factory, monkeypatch, stub_access, _stub_casual_llm, gate  # noqa: F811
):
    result = _say(session_factory, monkeypatch, stub_access, gate, _clear_all(gate), "clear all")
    _assert_the_reset_keeps_nothing_open(session_factory, result, _stub_casual_llm)


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


# --- G2 (contacts 13 and 18): a reset over an open pick is the seam's turn ------------------------
# Round 8 ruling: the parse's carried domain never reaches a model, because no casual / clarifier
# model is called on a reset at all.


def _stored_question(kind: str) -> dict[str, Any]:
    if kind == "customer_order_pick":
        options = [
            {"position": i, "label": f"SO90000{i}", "code": f"SO90000{i}", "uuid": ht.uuid_of(f"SO90000{i}"),
             "entity_type": "customer_order", "payload": {}}
            for i in (1, 2)
        ]
        pending = turn_pending.ask(kind, options, asked_at_turn=1, expects="pick",
                                   payload={"domain": "order", "domains": ["order"]})
        focus = Focus(domains=["order"])
    else:
        options = [
            {"position": i, "label": c, "code": c, "uuid": ht.uuid_of(c), "uuids": [ht.uuid_of(c)],
             "entity_type": "product", "payload": {}}
            for i, c in enumerate(TWENTY[:3], 1)
        ]
        pending = turn_pending.ask(kind, options, asked_at_turn=1, expects="pick",
                                   payload={"domain": "inventory", "domains": ["inventory"]})
        focus = Focus(products=ht.product_rows(TWENTY[0]), domains=["inventory"])
    return {**_stored_session(), "focus": focus_to_wire(focus), "open_question": turn_pending.to_wire(pending)}


def _say_over(session_factory, monkeypatch, stub_access, gate, session_vars, emission, words):  # noqa: F811
    _seed(session_factory, session_vars)
    _stub_parser(monkeypatch, gate, emission)
    stub_access()
    env = _envelope()
    env.message["message"]["message"]["text"] = words
    return engine_mod.run_turn(env, session_factory=session_factory)


def _field(prompt: str, name: str) -> str:
    line = next(row for row in prompt.splitlines() if row.startswith(f"{name}: "))
    return line[len(f"{name}: "):].strip()


RESET_OVER = pytest.mark.parametrize(
    "question,domain,intent",
    [("customer_order_pick", "order", "check_order"), ("product_pick", "product", "check_product")],
    ids=["customer_order_pick", "product_pick"],
)


@GATES
@RESET_OVER
def test_a_reset_over_a_pick_calls_no_small_talk_model_and_keeps_nothing_open(
    session_factory, monkeypatch, stub_access, _stub_casual_llm, gate, question, domain, intent  # noqa: F811
):
    emission = _parser_output(
        intent_hint=intent, domain_hint=domain, scope_intent=None, user_goal="clear all", match_mode=None,
        entities=[], entity_op="clear", broaden_axis="all", topic_reset=True, scope_exclusive=None,
        contains_flyer=None, correction=None, escalation={"is_escalation_confirmation": None, "company_pick": None},
        open_question_answer={"mode": None, "picked": [], "items": [], "qty_for_all": None},
    )
    if gate:
        emission["state_changes"] = [
            {"op": "close_question", "axis": None, "position": None},
            {"op": "new_subject", "axis": None, "position": None},
        ]
    result = _say_over(session_factory, monkeypatch, stub_access, gate, _stored_question(question), emission, "clear all")
    _assert_the_reset_keeps_nothing_open(session_factory, result, _stub_casual_llm)


@GATES
def test_guard_small_talk_that_is_not_a_reset_still_shows_the_parse_intent_and_domain(
    session_factory, monkeypatch, stub_access, _stub_casual_llm, gate  # noqa: F811
):
    """A bare "60" with nothing open is no subject (D34): it goes to small talk without being a
    reset, and the model sees the parse's own intent and domain and the stored session as before."""
    emission = _parser_output(
        intent_hint="check_stock", domain_hint="inventory", scope_intent=None, user_goal="60", match_mode=None,
        entities=[], entity_op=None, demand_qty=60, topic_reset=False, scope_exclusive=None, contains_flyer=None,
        correction=None, escalation={"is_escalation_confirmation": None, "company_pick": None},
        open_question_answer={"mode": None, "picked": [], "items": [], "qty_for_all": None},
    )
    if gate:
        emission["state_changes"] = []
    empty = {**_stored_session(), "focus": focus_to_wire(Focus()), "open_question": None}
    result = _say_over(session_factory, monkeypatch, stub_access, gate, empty, emission, "60")
    assert result.branch_kind == "low_signal", result.branch_kind
    prompt = _stub_casual_llm[-1]["user_prompt"]
    assert _field(prompt, "intent_hint") == "check_stock", prompt
    assert _field(prompt, "domain_hint") == "inventory", prompt
    assert _shown_session(prompt) == empty
