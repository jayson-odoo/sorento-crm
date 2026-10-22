"""CHAT-PICK-QTY-STATE release gate (#1829), round 7: ONE reset seam at the top of the turn path.

EVAL-BENCH 6335656904 (b173c6e8c4): "clear all" over stored sessions still ran a product
search (contacts 03, 05), hit the no-filter stock refusal (contact 01) and handed contact 13
(an open customer_order_pick) to a person (assign_conversation + add_comment). The domain and
message type the parser carries leaked into routing.

Crew ruling (design note 6335681391): right after the parse, before the state applier, apply,
routing or any lane, a turn that signals a reset (`topic_reset`, a cancel answer, `entity_op`
clear, a clear or new_subject op) and states nothing new (no entity of its own, no filter, no
date window, no position, pick or item quantity) is a reset: the open question, every task
and the stored list close, the focus resets to RESET_KEEPS, the session is saved and ONE
fixed acknowledgement goes out in the reply language. No lane, fetch, tool, escalation,
hand-off, small-talk model call or "Last time" recap. A reset that states an ask keeps
today's path.

Driven through `engine.run_turn` with the session stored on a synthetic contact, the parser
stubbed with the measured parses (v63 old path, v92 state path), the MCP tool and the
small-talk model recorded. Synthetic codes only.
"""
from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest
from sqlalchemy import text

from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import parser as parser_mod
from app.services.chatbot.turn import pending as turn_pending
from app.services.chatbot.turn.state import Focus, focus_to_wire
from tests.chatbot import _ht26_fixtures as ht
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output, stub_access  # noqa: F401

ACK = {
    "en": "Okay, I've cleared that. What would you like to check?",
    "ms": "Baik, saya sudah kosongkan. Apa yang anda mahu semak?",
    "zh": "好的，已清除。您想查询什么？",
}
HAND_OFF = {"assign_conversation", "add_comment"}

TWENTY = [f"SRTZQ{i:03d}" for i in range(1, 21)]
FOUR = ["SRTZA101", "SRTZA102", "SRTZA103", "SRTZA104"]


# --- the stored sessions --------------------------------------------------------------------------


def _team_offer():
    return turn_pending.ask(
        "team_pick", [{"position": 1, "label": "Yes", "entity_type": "team", "payload": {}}],
        team="warehouse", asked_at_turn=1, expects="yes_no",
    )


def _rows(codes):
    return [{"position": i, "label": c, "code": c, "uuid": ht.uuid_of(c), "entity_type": "product", "shown_at_turn": 1}
            for i, c in enumerate(codes, 1)]


def _stored(context: str) -> dict[str, Any]:
    pending = None
    if context == "C04":
        task = ht.stock_task([(c, None) for c in TWENTY], status="parked", opened_at_turn=0, touched_at_turn=0)
        focus = Focus(products=ht.product_rows(TWENTY[0]), domains=["inventory"], tasks=(task,),
                      last_list=_rows(TWENTY))
        pending = _team_offer()
    elif context == "C28":
        task = ht.stock_task([(c, None) for c in FOUR], status="open", opened_at_turn=1, touched_at_turn=1)
        focus = Focus(products=ht.product_rows(*FOUR), domains=["inventory"], tasks=(task,), last_list=_rows(FOUR))
    elif context == "C30":
        task = ht.stock_task([(FOUR[0], 10), (FOUR[1], None)], status="open", opened_at_turn=1, touched_at_turn=1)
        focus = Focus(products=ht.product_rows(*FOUR[:2]), domains=["inventory"], tasks=(task,),
                      last_list=_rows(FOUR[:2]))
    elif context in ("C01", "C03"):
        customer = {"raw": "ZZC001", "hint": "customer", "canonical_code": "ZZC001", "uuid": ht.uuid_of("ZZC001"),
                    "current_message": False, "confident": True}
        focus = Focus(customers=[customer] if context == "C03" else [], products=ht.product_rows(TWENTY[0]),
                      domains=["inventory"], brands=["SORENTO"])
        pending = _team_offer()
    elif context == "C13":
        options = [
            {"position": i, "label": f"SO90000{i}", "code": f"SO90000{i}", "uuid": ht.uuid_of(f"SO90000{i}"),
             "entity_type": "customer_order", "payload": {}}
            for i in (1, 2)
        ]
        pending = turn_pending.ask("customer_order_pick", options, asked_at_turn=1, expects="pick",
                                   payload={"domain": "order", "domains": ["order"]})
        focus = Focus(domains=["order"])
    elif context == "C18":
        options = [
            {"position": i, "label": c, "code": c, "uuid": ht.uuid_of(c), "uuids": [ht.uuid_of(c)],
             "entity_type": "product", "payload": {}}
            for i, c in enumerate(TWENTY[:3], 1)
        ]
        pending = turn_pending.ask("product_pick", options, asked_at_turn=1, expects="pick",
                                   payload={"domain": "inventory", "domains": ["inventory"]})
        focus = Focus(products=ht.product_rows(TWENTY[0]), domains=["inventory"], last_list=_rows(TWENTY[:3]))
    elif context == "nothing_open":
        focus = Focus()
    else:
        raise KeyError(context)
    return {
        "focus": focus_to_wire(focus),
        "open_question": turn_pending.to_wire(pending),
        "ideation": None,
        "access_levels": [],
        "contains_flyer": False,
        "reply_language": None,
    }


# --- the parses ---------------------------------------------------------------------------------------

#: What the parser carried beside "clear all" per contact (measured): the domain and type leaked.
CARRIED = {
    "C01": dict(domain_hint="inventory", intent_hint="check_stock", domain_in_message=True),
    "C03": dict(domain_hint="product", intent_hint="check_product", message_type="business_query"),
    "C13": dict(domain_hint="order", intent_hint="check_order", message_type="business_query"),
}


def _op(op, axis=None):
    return {"op": op, "axis": axis, "position": None}


SHAPES = {
    # v63, the old path.
    "v63_reset_cancel": dict(topic_reset=True, mode="cancel", changes=None),
    "v63_cancel": dict(topic_reset=False, mode="cancel", changes=None),
    # v92, the state path.
    "v92_cancel_ops": dict(topic_reset=False, mode="cancel", changes=[_op("clear", "product"), _op("close_question")]),
    "v92_new_subject_clear_customer": dict(topic_reset=False, mode=None, domain_hint="order", intent_hint="check_order",
                                           changes=[_op("new_subject"), _op("clear", "customer")]),
}
OLD, STATE = ["v63_reset_cancel", "v63_cancel"], ["v92_cancel_ops", "v92_new_subject_clear_customer"]
CONTEXTS = ["C04", "C28", "C30", "C01", "C03", "C13", "C18", "nothing_open"]


def _clear_all(context: str, shape: str) -> dict[str, Any]:
    spec = dict(SHAPES[shape])
    changes, mode = spec.pop("changes"), spec.pop("mode")
    fields = {"domain_hint": None, "intent_hint": None, **CARRIED.get(context, {}), **spec}
    emission = _parser_output(
        scope_intent=None, user_goal="clear all", match_mode=None, entities=[], entity_op="clear", broaden_axis="all",
        scope_exclusive=None, contains_flyer=None, correction=None,
        escalation={"is_escalation_confirmation": None, "company_pick": None},
        open_question_answer={"mode": mode, "picked": [], "items": [], "qty_for_all": None},
        **fields,
    )
    if changes is not None:
        emission["state_changes"] = changes
    return emission


# --- the harness ------------------------------------------------------------------------------------


class Turn:
    def __init__(self, session_factory, monkeypatch, stub_access, casual_calls, *, gate: bool):  # noqa: F811
        self.session_factory = session_factory
        self.monkeypatch = monkeypatch
        self.stub_access = stub_access
        self.casual_calls = casual_calls
        self.gate = gate
        self.tool_calls: list[tuple[str, dict[str, Any]]] = []
        self.plans: list[Any] = []

    def say(self, session_vars: dict[str, Any], emission: dict[str, Any], words: str = "clear all"):
        db = self.session_factory()
        db.execute(
            text("INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
                 "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"),
            {"cid": str(CONTACT_ID), "phone": "+60000000009", "sv": json.dumps(session_vars)},
        )
        db.commit()
        gate = self.gate

        def fake_resolve_config(db, *, current_date, override_version_id=None):
            cfg = parser_mod.ParserConfig(system_prompt="stub", prompt_version=1, provider="openai",
                                          model="gpt-test", api_key="sk-test")
            return dataclasses.replace(cfg, state_block=True) if gate else cfg

        from app.services.ai_assistant_service import MCPRuntimeClient

        def record_tool(client, name, args):
            self.tool_calls.append((name, args))
            return json.dumps({"answers": []})

        real_apply = engine_mod.turn_apply

        def spy_apply(*a, **k):
            out = real_apply(*a, **k)
            self.plans.append(out[1])
            return out

        self.monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
        self.monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: emission)
        self.monkeypatch.setattr(MCPRuntimeClient, "call_tool", record_tool)
        self.monkeypatch.setattr(engine_mod, "turn_apply", spy_apply)
        self.stub_access()
        env = _envelope()
        env.message["message"]["message"]["text"] = words
        return engine_mod.run_turn(env, session_factory=self.session_factory)

    def stored_after(self) -> dict[str, Any]:
        return self.session_factory().execute(
            text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :cid"), {"cid": str(CONTACT_ID)}
        ).scalar() or {}

    def trace_of(self, result) -> str:
        row = self.session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
        return json.dumps(row.trace, default=str)


@pytest.fixture()
def turn(session_factory, monkeypatch, stub_access, _stub_casual_llm, request):  # noqa: F811
    def make(gate: bool) -> Turn:
        return Turn(session_factory, monkeypatch, stub_access, _stub_casual_llm, gate=gate)

    return make


def _assert_the_reset_turn(t: Turn, result, stored_before: dict[str, Any], language: str = "en"):
    assert (result.reply or {}).get("text") == ACK[language], (result.branch_kind, (result.reply or {}).get("text"))
    kinds = [a.get("kind") for a in result.actions or []]
    assert not HAND_OFF & set(kinds), kinds
    assert kinds == ["send_message"], kinds
    assert not t.tool_calls, t.tool_calls
    assert not t.plans, "apply ran on a reset turn"
    assert not t.casual_calls, "the small-talk model was called on a reset turn"
    after = t.stored_after()
    assert after.get("open_question") is None, after.get("open_question")
    focus = after.get("focus") or {}
    assert not focus.get("tasks"), focus.get("tasks")
    assert not focus.get("last_list"), focus.get("last_list")
    kept = stored_before["focus"]
    assert focus == focus_to_wire(Focus(tier=list(kept.get("tier") or []), brands=list(kept.get("brands") or []))), focus
    assert "reset_turn" in t.trace_of(result)


CASES = pytest.mark.parametrize(
    "gate,shape",
    [(False, s) for s in OLD] + [(True, s) for s in STATE],
    ids=[f"old_path-{s}" for s in OLD] + [f"state_path-{s}" for s in STATE],
)


@CASES
@pytest.mark.parametrize("context", CONTEXTS)
def test_clear_all_is_one_reset_turn(turn, context, gate, shape):
    t = turn(gate)
    stored = _stored(context)
    result = t.say(stored, _clear_all(context, shape))
    _assert_the_reset_turn(t, result, stored)


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
@pytest.mark.parametrize("language,words", [("ms", "kosongkan semua"), ("zh", "全部清除")])
def test_the_reset_acknowledgement_is_in_the_reply_language(turn, gate, language, words):
    t = turn(gate)
    stored = {**_stored("C04"), "reply_language": language}
    result = t.say(stored, _clear_all("C04", STATE[0] if gate else OLD[0]), words)
    _assert_the_reset_turn(t, result, stored, language)


# --- guards: what is no reset keeps today's path --------------------------------------------------


def _stated(code):
    return {"raw": code, "hint": "product", "canonical_code": code, "current_message": True, "confident": True,
            "hint_confident": True}


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
def test_guard_a_reset_that_states_a_product_still_fetches_it(turn, gate):
    """"forget that, check SRTZA101": a reset with its own ask runs that ask."""
    t = turn(gate)
    emission = _parser_output(domain_hint="inventory", intent_hint="check_stock", entities=[_stated(FOUR[0])],
                              entity_op="replace", topic_reset=True, scope_intent=None, match_mode=None,
                              open_question_answer={"mode": None, "picked": [], "items": [], "qty_for_all": None})
    if gate:
        emission["state_changes"] = [_op("new_subject"), _op("set", "product")]
    result = t.say(_stored("C28"), emission, "forget that, check SRTZA101")
    assert (result.reply or {}).get("text") != ACK["en"]
    fetched = [e.get("canonical_code") for plan in t.plans for spec in plan.fetch for e in spec.entities]
    assert FOUR[0] in fetched, (fetched, [p.trace.rules_fired for p in t.plans])


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
def test_guard_a_plain_no_over_an_offer_still_declines(turn, gate):
    t = turn(gate)
    emission = _parser_output(domain_hint="inventory", intent_hint="check_stock", entities=[], topic_reset=False,
                              is_affirmative=False, scope_intent=None, match_mode=None, entity_op=None,
                              open_question_answer={"mode": "no", "picked": [], "items": [], "qty_for_all": None})
    if gate:
        emission["state_changes"] = [_op("answer")]
    result = t.say(_stored("C01"), emission, "no")
    assert result.branch_kind == "escalation_declined", (result.branch_kind, (result.reply or {}).get("text"))
    assert (result.reply or {}).get("text") != ACK["en"]


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
def test_guard_a_normal_stock_ask_is_untouched(turn, gate):
    t = turn(gate)
    emission = _parser_output(domain_hint="inventory", intent_hint="check_stock", entities=[_stated("ZZP999")],
                              entity_op="replace", topic_reset=False, scope_intent=None, match_mode=None,
                              open_question_answer={"mode": None, "picked": [], "items": [], "qty_for_all": None})
    if gate:
        emission["state_changes"] = [_op("set", "product")]
    result = t.say(_stored("nothing_open"), emission, "check stock ZZP999")
    assert (result.reply or {}).get("text") != ACK["en"]
    assert t.plans, "apply never ran on a stock ask"
    assert "reset_turn" not in t.trace_of(result)


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
def test_guard_a_thanks_is_still_small_talk(turn, gate):
    t = turn(gate)
    emission = _parser_output(message_type="confirmation", domain_hint=None, intent_hint=None, entities=[],
                              entity_op=None, topic_reset=False, scope_intent=None, match_mode=None,
                              open_question_answer={"mode": None, "picked": [], "items": [], "qty_for_all": None})
    if gate:
        emission["state_changes"] = []
    result = t.say(_stored("C01"), emission, "thanks")
    assert result.branch_kind == "low_signal", result.branch_kind
    assert t.casual_calls, "the small-talk model was not called"
    assert (result.reply or {}).get("text") != ACK["en"]
    assert "reset_turn" not in t.trace_of(result)
