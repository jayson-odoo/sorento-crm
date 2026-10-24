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


CLEAR_ALL_CASES = [
    (context, gate, shape)
    for gate, shape in [(False, s) for s in OLD] + [(True, s) for s in STATE]
    for context in CONTEXTS
    # Excluded: a constructed C01 x v92-customer-order cross the parser was never measured producing.
    if (context, shape) != ("C01", "v92_new_subject_clear_customer")
]


@pytest.mark.parametrize(
    "context,gate,shape", CLEAR_ALL_CASES,
    ids=[f"{c}-{'state_path' if g else 'old_path'}-{s}" for c, g, s in CLEAR_ALL_CASES],
)
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


# --- round 8: the seam's two predicates, narrowed, and the episode a reset closes ----------------------
#
# Opus reviewer + captain measurement on a7736d3402: `entity_op` clear (the parser's "all" / broaden
# signal), a `clear` op (one part of the subject) and a `new_subject` op beside a domain the message
# names were read as resets, and the seam answered before the memory episode write. Rules (brief round
# 8): a reset is `topic_reset`, a cancel, or a `new_subject` naming no domain of its own; a domain the
# message names, `asks`, `top_n`, `rank_by`, `basis`, `sort_by`, `group_by`, a named `broaden_axis`,
# `scope_intent`, `query_brands`, a `set` op, `qty_for_all` or a hand-off / history / idea message type
# also state something new and keep today's path. A reset closes the episode as the routed reset did.


def _customer_pick():
    options = [
        {"position": i, "label": f"ZZC00{i}", "code": f"ZZC00{i}", "uuid": ht.uuid_of(f"ZZC00{i}"),
         "entity_type": "customer", "payload": {}}
        for i in (1, 2, 3)
    ]
    pending = turn_pending.ask("customer_pick", options, asked_at_turn=1, expects="pick",
                               payload={"domain": "order", "domains": ["order"]})
    return {
        "focus": focus_to_wire(Focus(domains=["order"])),
        "open_question": turn_pending.to_wire(pending),
        "ideation": None,
        "access_levels": [],
        "contains_flyer": False,
        "reply_language": None,
    }


def _no_answer(mode=None):
    return {"mode": mode, "picked": [], "items": [], "qty_for_all": None}


def _read(ops, **fields):
    """One guard's parse: every field "said nothing" except the ones given; `ops` is the v92
    `state_changes` (the state path only)."""
    base = dict(message_type="business_query", domain_hint=None, intent_hint=None, entities=[], entity_op=None,
                topic_reset=False, scope_intent=None, match_mode=None, broaden_axis=None,
                open_question_answer=_no_answer())
    base.update(fields)
    return _parser_output(**base), ops


#: (stored context, words, parse fields, v92 ops, paths): none of these is a reset, each routes as at
#: b173c6e8c4. `None` paths means both.
GUARDS = {
    # "all" over a numbered customer picker (outstanding, sales report, top selling): the picker's all.
    "all_over_a_customer_picker": ("customer_pick", "all", dict(
        message_type="casual", entity_op="clear", broaden_axis="all", scope_intent="broaden"), [], None),
    # Availability "all" / "all of them" over the product list: a broaden alone (S30, S31).
    "all_over_a_product_pick": ("C18", "all", dict(
        domain_hint="inventory", intent_hint="check_stock", entity_op="clear", broaden_axis="all",
        open_question_answer=_no_answer("all")), [], None),
    "show_all_stock": ("nothing_open", "show all stock", dict(
        domain_hint="inventory", intent_hint="check_stock", domain_in_message=True, entity_op="clear",
        broaden_axis="all", scope_intent="broaden"), [_op("new_subject")], None),
    # v92: a new subject beside a domain the message names is a new ask.
    "any_promotions": ("C28", "any promotions?", dict(
        domain_hint="promotion", intent_hint="check_promotion", domain_in_message=True), [_op("new_subject")], [True]),
    "top_10_sellers": ("C28", "top 10 sellers", dict(
        domain_hint="order", intent_hint="check_order", domain_in_message=True, top_n=10), [_op("new_subject")], [True]),
    "sort_by_price": ("C28", "sort by price", dict(
        domain_hint="master_products", intent_hint="check_product", domain_in_message=True,
        requested_attributes=[]), [_op("new_subject")], [True]),
    # One part of the subject widened: no reset.
    "for_all_customers": ("C03", "for all customers", dict(
        domain_hint="inventory", intent_hint="check_stock", entity_op="clear", broaden_axis="customer",
        broaden_to="all"), [_op("clear", "customer")], None),
    "any_brand": ("C03", "any brand", dict(
        domain_hint="inventory", intent_hint="check_stock", entity_op="clear", broaden_axis="brand",
        broaden_to="all"), [_op("clear", "brand")], None),
    # A reset AND a new ask: the ask is answered.
    "never_mind_any_promotions": ("C28", "never mind, any promotions?", dict(
        domain_hint="promotion", intent_hint="check_promotion", domain_in_message=True, topic_reset=True),
        [_op("new_subject")], None),
    "cancel_talk_to_a_person": ("C04", "cancel, talk to a person", dict(
        message_type="request_for_help", open_question_answer=_no_answer("cancel")), [_op("close_question")], None),
    "an_idea": ("nothing_open", "I have an idea: a dark mode for the dealer portal", dict(
        domain_hint="ideate", intent_hint="submit_idea", entity_op="clear"), [], None),
    "a_cold_all_of_them": ("nothing_open", "all of them", dict(
        message_type="clarification", entity_op="clear", broaden_axis="all", scope_intent="broaden"), [], None),
}

#: The lane each guard took at b173c6e8c4 (no seam), on both paths (measured 22 Oct).
B173_LANE = {
    "all_over_a_customer_picker": "business_query", "all_over_a_product_pick": "business_query",
    "show_all_stock": "business_query",
    "any_promotions": "check_promotion", "top_10_sellers": "business_query", "sort_by_price": "business_query",
    "for_all_customers": "business_query", "any_brand": "business_query",
    "never_mind_any_promotions": "check_promotion", "cancel_talk_to_a_person": None, "an_idea": "ideate",
    "a_cold_all_of_them": "clarify_menu",
}

GUARD_CASES = [
    (name, gate)
    for name, spec in GUARDS.items()
    for gate in (spec[4] if spec[4] is not None else [False, True])
]


@pytest.mark.parametrize(
    "name,gate", GUARD_CASES, ids=[f"{n}-{'state_path' if g else 'old_path'}" for n, g in GUARD_CASES]
)
def test_round8_guard_no_reset_keeps_todays_path(turn, name, gate):
    context, words, fields, ops, _paths = GUARDS[name]
    t = turn(gate)
    emission, ops = _read(ops, **fields)
    if gate:
        emission["state_changes"] = ops
    stored = _customer_pick() if context == "customer_pick" else _stored(context)
    result = t.say(stored, emission, words)
    assert (result.reply or {}).get("text") != ACK["en"], (result.branch_kind, (result.reply or {}).get("text"))
    assert "reset_turn" not in t.trace_of(result), "the reset seam answered a turn that is no reset"
    assert t.plans, "apply never ran: the turn did not take today's path"
    assert result.branch_kind == B173_LANE[name], (result.branch_kind, (result.reply or {}).get("text"))


# --- round 8: a reset closes the memory episode, as the routed reset did --------------------------------


class Conversation(Turn):
    """Several turns on ONE stored contact (`Turn.say` seeds a fresh contact row every call)."""

    def seed(self, session_vars: dict[str, Any]) -> None:
        db = self.session_factory()
        db.execute(
            text("INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
                 "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"),
            {"cid": str(CONTACT_ID), "phone": "+60000000019", "sv": json.dumps(session_vars)},
        )
        db.commit()

    def run(self, emission: dict[str, Any], words: str, message_id: str, **envelope_overrides):
        gate = self.gate

        def fake_resolve_config(db, *, current_date, override_version_id=None):
            cfg = parser_mod.ParserConfig(system_prompt="stub", prompt_version=1, provider="openai",
                                          model="gpt-test", api_key="sk-test")
            return dataclasses.replace(cfg, state_block=True) if gate else cfg

        from app.services.ai_assistant_service import MCPRuntimeClient

        self.monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
        self.monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: emission)
        self.monkeypatch.setattr(MCPRuntimeClient, "call_tool", lambda client, name, args: json.dumps({"answers": []}))
        self.stub_access()
        env = _envelope(**envelope_overrides)
        env.message["message"]["messageId"] = message_id
        env.message["message"]["message"]["text"] = words
        return engine_mod.run_turn(env, session_factory=self.session_factory)

    def stamp_before_now(self, turn_id: str, minutes: int) -> None:
        """Every session of one test shares one outer transaction, so every turn's created_at is
        that transaction's now(): turns would tie in the episode's ORDER BY created_at. A live
        turn stamped `minutes` before now() keeps its place, ahead of the reset turn's own."""
        from datetime import timedelta

        from sqlalchemy import func

        db = self.session_factory()
        db.query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).update(
            {"created_at": func.now() - timedelta(minutes=minutes)}, synchronize_session=False
        )
        db.commit()

    def frames(self, is_test: bool):
        from app.models.conversation_frame import ConversationFrame

        return (
            self.session_factory().query(ConversationFrame)
            .filter(ConversationFrame.contact_respond_id == str(CONTACT_ID), ConversationFrame.is_test.is_(is_test))
            .all()
        )

    def memory_episodes(self, result) -> dict[str, Any]:
        row = self.session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
        records = [r for r in (row.trace or []) if isinstance(r, dict) and r.get("kind") == "memory"]
        assert records, "no memory record on the turn"
        return records[-1].get("episodes") or {}


def _stock_ask(code: str, gate: bool) -> dict[str, Any]:
    emission = _parser_output(domain_hint="inventory", intent_hint="check_stock", entities=[_stated(code)],
                              entity_op="replace", topic_reset=False, scope_intent=None, match_mode=None,
                              open_question_answer=_no_answer())
    if gate:
        emission["state_changes"] = [_op("new_subject"), _op("set", "product")]
    return emission


@pytest.fixture()
def conversation(session_factory, monkeypatch, stub_access, _stub_casual_llm):  # noqa: F811
    def make(gate: bool) -> Conversation:
        return Conversation(session_factory, monkeypatch, stub_access, _stub_casual_llm, gate=gate)

    return make


@CASES
def test_round8_a_reset_after_live_turns_closes_the_episode(conversation, gate, shape):
    c = conversation(gate)
    c.seed(_stored("nothing_open"))
    first = c.run(_stock_ask(FOUR[0], gate), f"check stock {FOUR[0]}", "ZZT-r8-ep-1")
    second = c.run(_stock_ask(FOUR[1], gate), f"check stock {FOUR[1]}", "ZZT-r8-ep-2")
    c.stamp_before_now(first.turn_id, 2)
    c.stamp_before_now(second.turn_id, 1)
    reset = c.run(_clear_all("C28", shape), "clear all", "ZZT-r8-ep-3")
    assert (reset.reply or {}).get("text") == ACK["en"], (reset.branch_kind, (reset.reply or {}).get("text"))
    frames = c.frames(is_test=False)
    assert len(frames) == 1, f"a reset after two live turns closes one episode, got {len(frames)}"
    assert list(frames[0].turn_ids) == [first.turn_id, second.turn_id], list(frames[0].turn_ids)
    assert frames[0].close_reason == "topic_switch", frames[0].close_reason
    written = c.memory_episodes(reset).get("written")
    assert isinstance(written, dict) and written.get("trigger") == "topic_reset", written
    assert written.get("turn_count") == 2, written


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
def test_round8_a_console_dry_run_reset_writes_one_is_test_frame_and_nothing_else(conversation, gate):
    c = conversation(gate)
    c.seed(_stored("nothing_open"))
    console = {"is_test": True, "ingress": "console"}
    c.run(_stock_ask(FOUR[0], gate), f"check stock {FOUR[0]}", "ZZT-r8-console-1", **console)
    usage_before = c.session_factory().execute(text("SELECT count(*) FROM ai_assistant_usage_logs")).scalar()
    stored_before = c.stored_after()
    reset = c.run(_clear_all("C28", STATE[0] if gate else OLD[0]), "clear all", "ZZT-r8-console-2", **console)
    assert (reset.reply or {}).get("text") == ACK["en"], (reset.branch_kind, (reset.reply or {}).get("text"))
    frames = c.frames(is_test=True)
    assert len(frames) == 1, f"a console dry run reset writes one is_test frame, got {len(frames)}"
    assert not c.frames(is_test=False), "a console dry run wrote a live frame"
    usage_after = c.session_factory().execute(text("SELECT count(*) FROM ai_assistant_usage_logs")).scalar()
    assert usage_after == usage_before, "a console dry run must write nothing outside chatbot.turns"
    assert c.stored_after() == stored_before, "a console dry run saved the session"


# --- round 9: a domain beside "all" is the held one only when the session holds it --------------------
#
# Reviewer S2 on 207fb5d5de: "never mind, all promotions" (topic_reset, domain promotion, broaden_axis
# all) over a stock session got the acknowledgement, because the round 8 carve-out read every domain
# beside "all" as the held one. Captain ruling (option B): the carve-out holds only when the session
# already holds that domain, contact 01's own shape (inventory over an inventory session).


def _beside_all(domain: str, intent: str, gate: bool) -> dict[str, Any]:
    emission = _parser_output(
        domain_hint=domain, intent_hint=intent, domain_in_message=True, topic_reset=True, entities=[],
        entity_op="clear", broaden_axis="all", scope_intent=None, match_mode=None,
        open_question_answer=_no_answer(),
    )
    if gate:
        emission["state_changes"] = [_op("new_subject")]
    return emission


#: What "never mind, all promotions" over a stock session did at b173c6e8c4 (no seam), both paths.
B173_ALL_PROMOTIONS = {"lane": "check_promotion", "actions": ["send_message"], "tools": []}


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
def test_round9_guard_never_mind_all_promotions_over_a_stock_session_runs_the_promotion_lane(turn, gate):
    t = turn(gate)
    result = t.say(_stored("C28"), _beside_all("promotion", "check_promotion", gate), "never mind, all promotions")
    assert (result.reply or {}).get("text") != ACK["en"], (result.branch_kind, (result.reply or {}).get("text"))
    assert "reset_turn" not in t.trace_of(result), "the reset seam answered a turn that names its own domain"
    assert t.plans, "apply never ran: the turn did not take today's path"
    observed = {
        "lane": result.branch_kind,
        "actions": [a.get("kind") for a in result.actions or []],
        "tools": sorted({name for name, _ in t.tool_calls}),
    }
    assert observed == B173_ALL_PROMOTIONS, observed


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
def test_round9_contact_01s_shape_inventory_beside_all_over_an_inventory_session_still_resets(turn, gate):
    t = turn(gate)
    stored = _stored("C01")
    result = t.say(stored, _beside_all("inventory", "check_stock", gate), "clear all")
    _assert_the_reset_turn(t, result, stored)


# --- round 10: a reset wins over broaden --------------------------------------------------------------
#
# Crew audit 22 Oct on 789c8cc1f1: "clear all" parsed with topic_reset true AND scope_intent "broaden"
# skipped the seam (round 8 counted scope_intent broaden as stated), fell to the old path and got the
# low_signal small-talk "Last time ..." reply. Crew rule: when topic_reset is true, neither scope_intent
# broaden nor broaden_axis all states anything. A domain the session does not hold, a named broaden
# axis, and scope_intent broaden without topic_reset still count.

#: The held domain of each stored context (None: the session holds no domain).
HELD_DOMAIN = {"C04": "inventory", "C28": "inventory", "C13": "order", "nothing_open": None}
R10_SHAPES = {
    "broaden": dict(scope_intent="broaden", broaden_axis=None),
    "broaden_all": dict(scope_intent="broaden", broaden_axis="all"),
}


def _reset_beside_broaden(shape: str, domain: str | None, gate: bool) -> dict[str, Any]:
    named = dict(domain_hint=domain, intent_hint=None, domain_in_message=True) if domain else dict(
        domain_hint=None, intent_hint=None)
    emission = _parser_output(
        user_goal="clear all", entities=[], entity_op="clear", topic_reset=True, match_mode=None,
        open_question_answer=_no_answer(), **R10_SHAPES[shape], **named,
    )
    if gate:
        emission["state_changes"] = [_op("clear", "customer"), _op("clear", "period")]
    return emission


R10_CASES = [
    (context, shape, with_domain, gate)
    for context, held in HELD_DOMAIN.items()
    for shape in R10_SHAPES
    for with_domain in ([False, True] if held else [False])
    for gate in (False, True)
]


@pytest.mark.parametrize(
    "context,shape,with_domain,gate", R10_CASES,
    ids=[f"{c}-{s}-{'held_domain' if d else 'no_domain'}-{'state_path' if g else 'old_path'}"
         for c, s, d, g in R10_CASES],
)
def test_round10_a_reset_beside_broaden_is_one_reset_turn(turn, context, shape, with_domain, gate):
    t = turn(gate)
    stored = _stored(context)
    domain = HELD_DOMAIN[context] if with_domain else None
    result = t.say(stored, _reset_beside_broaden(shape, domain, gate), "clear all")
    assert "Last time" not in ((result.reply or {}).get("text") or ""), (result.reply or {}).get("text")
    _assert_the_reset_turn(t, result, stored)


def _lane_actions_tools(t: Turn, result) -> dict[str, Any]:
    return {
        "lane": result.branch_kind,
        "actions": [a.get("kind") for a in result.actions or []],
        "tools": sorted({name for name, _ in t.tool_calls}),
    }


#: What each round 10 guard did at b173c6e8c4 (no seam), both paths (measured 22 Oct).
B173_R10 = {
    "show_me_everything": {"lane": "business_query", "actions": ["send_message"], "tools": []},
    "never_mind_all_promotions_broaden": {"lane": "check_promotion", "actions": ["send_message"], "tools": []},
    "reset_with_a_named_axis": {"lane": "low_signal", "actions": ["send_message"], "tools": []},
}


def _r10_guard(name: str, gate: bool) -> tuple[str, dict[str, Any], str]:
    if name == "show_me_everything":
        # No reset: a widening of the held stock ask.
        emission = _parser_output(
            domain_hint="inventory", intent_hint="check_stock", domain_in_message=True, entities=[],
            entity_op="clear", broaden_axis="all", scope_intent="broaden", topic_reset=False, match_mode=None,
            open_question_answer=_no_answer(),
        )
        ops, context, words = [], "C28", "show me everything"
    elif name == "never_mind_all_promotions_broaden":
        emission = _parser_output(
            domain_hint="promotion", intent_hint="check_promotion", domain_in_message=True, entities=[],
            entity_op="clear", broaden_axis="all", scope_intent="broaden", topic_reset=True, match_mode=None,
            open_question_answer=_no_answer(),
        )
        ops, context, words = [_op("new_subject")], "C28", "never mind, all promotions"
    else:
        emission = _parser_output(
            domain_hint="inventory", intent_hint="check_stock", entities=[], entity_op="clear",
            broaden_axis="customer", broaden_to="all", scope_intent=None, topic_reset=True, match_mode=None,
            open_question_answer=_no_answer(),
        )
        ops, context, words = [_op("clear", "customer")], "C03", "forget it, for all customers"
    if gate:
        emission["state_changes"] = ops
    return context, emission, words


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
@pytest.mark.parametrize("name", list(B173_R10))
def test_round10_guard_routes_as_at_b173(turn, name, gate):
    t = turn(gate)
    context, emission, words = _r10_guard(name, gate)
    result = t.say(_stored(context), emission, words)
    assert (result.reply or {}).get("text") != ACK["en"], (result.branch_kind, (result.reply or {}).get("text"))
    assert "reset_turn" not in t.trace_of(result), "the reset seam answered a turn that is no reset"
    assert t.plans, "apply never ran: the turn did not take today's path"
    assert _lane_actions_tools(t, result) == B173_R10[name], _lane_actions_tools(t, result)


# --- round 10, measured: the v63 reset+broaden parse over an open offer and a filled+parked check ---------
#
# Measured live 22 Oct (3 of 9 runs over offer shapes): "clear all" read as topic_reset true, a cancel,
# scope_intent broaden, broaden_axis all, entity_op clear, no domain, domain_in_message false and a
# plain business query. The state path gets the same read with no state ops.

FILLED, EMPTY = "CWCX605-RL-SOFT", "CWCX605-RL"
PARKED = ["BRSHP7098BW-1-07", "M311", "M312"]


def _measured_stored(context: str) -> dict[str, Any]:
    pending = None
    if context == "C01":
        # An open warehouse escalation offer (one option, Yes), nothing else held.
        focus = Focus()
        pending = _team_offer()
    else:
        # C30: the open stock check, line 1 filled and line 2 owed, beside a parked one of other codes.
        open_task = ht.stock_task([(FILLED, 10), (EMPTY, None)], status="open", opened_at_turn=2, touched_at_turn=2)
        parked = ht.stock_task([(c, None) for c in PARKED], status="parked", opened_at_turn=1, touched_at_turn=1)
        focus = Focus(products=ht.product_rows(FILLED, EMPTY), domains=["inventory"], tasks=(open_task, parked),
                      last_list=_rows([FILLED, EMPTY]))
    return {
        "focus": focus_to_wire(focus),
        "open_question": turn_pending.to_wire(pending),
        "ideation": None,
        "access_levels": [],
        "contains_flyer": False,
        "reply_language": None,
    }


def _measured_reset_broaden(gate: bool) -> dict[str, Any]:
    emission = _parser_output(
        topic_reset=True, open_question_answer=_no_answer("cancel"), scope_intent="broaden", broaden_axis="all",
        entity_op="clear", domain_hint=None, intent_hint=None, domain_in_message=False,
        message_type="business_query", user_goal="clear all", entities=[], match_mode=None,
    )
    if gate:
        emission["state_changes"] = []
    return emission


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
@pytest.mark.parametrize("context", ["C01", "C30"])
def test_round10_measured_reset_broaden_parse_resets_everything(turn, context, gate):
    t = turn(gate)
    stored = _measured_stored(context)
    result = t.say(stored, _measured_reset_broaden(gate), "clear all")
    reply = (result.reply or {}).get("text") or ""
    assert reply == ACK["en"], (result.branch_kind, reply)
    assert "That would search every stock" not in reply, reply
    assert "How many units" not in reply, reply
    assert not t.tool_calls, t.tool_calls
    assert not t.casual_calls, "a model was called on a reset turn"
    after = t.stored_after()
    assert after.get("open_question") is None, after.get("open_question")
    focus = after.get("focus") or {}
    assert not focus.get("tasks"), focus.get("tasks")
    assert not focus.get("last_list"), focus.get("last_list")
    _assert_the_reset_turn(t, result, stored)


# --- round 11: a cancel wins over broaden too ----------------------------------------------------------
#
# Reviewer grid proof on 58e2fbee45: the v63 "clear all" over an offer read as topic_reset FALSE, a
# cancel, scope_intent broaden, broaden_axis all, entity_op clear, no domain, domain_in_message false,
# a plain business query missed the seam (round 10 lifted broaden only beside topic_reset), fell to the
# apply reset and the small-talk "Last time ..." reply: the likely route to contact 30 run 2's re-asked
# quantity list. Rule: scope_intent broaden states nothing beside topic_reset OR a declared cancel.


def _measured_cancel_broaden(gate: bool, domain: str | None = None) -> dict[str, Any]:
    emission = {**_measured_reset_broaden(gate), "topic_reset": False}
    if domain:
        emission.update(domain_hint=domain, intent_hint="check_stock", domain_in_message=True)
    return emission


#: (context, the held domain stated beside the cancel or None).
R11_CASES = [(c, d, g) for c, d in [("C01", None), ("C30", None), ("C30", "inventory")] for g in (False, True)]


@pytest.mark.parametrize(
    "context,domain,gate", R11_CASES,
    ids=[f"{c}-{'held_domain' if d else 'no_domain'}-{'state_path' if g else 'old_path'}" for c, d, g in R11_CASES],
)
def test_round11_measured_cancel_broaden_parse_resets_everything(turn, context, domain, gate):
    t = turn(gate)
    stored = _measured_stored(context)
    result = t.say(stored, _measured_cancel_broaden(gate, domain), "clear all")
    reply = (result.reply or {}).get("text") or ""
    assert reply == ACK["en"], (result.branch_kind, reply)
    assert "How many units" not in reply, reply
    assert "Last time" not in reply, reply
    assert not t.casual_calls, "the small-talk model was called on a reset turn"
    assert not (t.stored_after().get("focus") or {}).get("tasks"), "a task was left"
    _assert_the_reset_turn(t, result, stored)


#: "cancel, show all promotions" over a stock session with an open offer, at b173c6e8c4 (both paths).
B173_CANCEL_ALL_PROMOTIONS = {"lane": "check_promotion", "actions": ["send_message"], "tools": []}


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
def test_round11_guard_cancel_show_all_promotions_over_a_stock_session_runs_promotions(turn, gate):
    t = turn(gate)
    emission = _parser_output(
        topic_reset=False, open_question_answer=_no_answer("cancel"), scope_intent="broaden", broaden_axis="all",
        entity_op="clear", domain_hint="promotion", intent_hint="check_promotion", domain_in_message=True,
        message_type="business_query", user_goal="show all promotions", entities=[], match_mode=None,
    )
    if gate:
        emission["state_changes"] = [_op("close_question"), _op("new_subject")]
    result = t.say(_stored("C04"), emission, "cancel, show all promotions")
    assert (result.reply or {}).get("text") != ACK["en"], (result.branch_kind, (result.reply or {}).get("text"))
    assert "reset_turn" not in t.trace_of(result), "the reset seam answered a turn that names its own domain"
    assert t.plans, "apply never ran: the turn did not take today's path"
    assert _lane_actions_tools(t, result) == B173_CANCEL_ALL_PROMOTIONS, _lane_actions_tools(t, result)


# --- round 12: an all-broaden over a session with nothing open is a reset --------------------------------
#
# EVAL-BENCH trace (contacts 01, 02, 30): the v63 "clear all" read as a plain business query,
# topic_reset false, entity_op clear, broaden_axis all, broaden_to all, scope_intent null, no domain,
# domain_in_message false, no answer, no entity, over a session with nothing open, no task and no list
# but a held subject. No reset signal fired: reuse_alive, broaden_all_clears_product, then the "That
# would search every stock we have" refusal (01, 02), or with the held product rows unsettled the
# resolver re-read them into a 10-line "How many units for each?" task (30). Captain ruling (option A):
# an all-broaden with scope_intent null and no domain or asks of its own, stating nothing else, over a
# session with no open question, no task of any status and no last_list, is a reset; a held subject is
# allowed. Synthetic codes stand in for the trace's.

HELD_TEN = TWENTY[:10]


def _measured_all_broaden(gate: bool, **overrides) -> dict[str, Any]:
    fields = dict(
        message_type="business_query", topic_reset=False, entity_op="clear", broaden_axis="all", broaden_to="all",
        scope_intent=None, domain_hint=None, intent_hint=None, domain_in_message=False,
        open_question_answer=_no_answer(), entities=[], reference_positions=[], demand_qty=None, match_mode=None,
        user_goal="clear all",
    )
    fields.update(overrides)
    emission = _parser_output(**fields)
    if gate:
        emission["state_changes"] = []
    return emission


def _held_subject(settled: bool = True) -> dict[str, Any]:
    """Products and the inventory domain held, nothing open, no task, no list. `settled` false: the
    product rows carry no uuid, so a turn that reuses them sends them back to the resolver."""
    rows = ht.product_rows(*HELD_TEN)
    if not settled:
        rows = [{k: v for k, v in row.items() if k != "uuid"} for row in rows]
    return {
        "focus": focus_to_wire(Focus(products=rows, domains=["inventory"])),
        "open_question": None,
        "ideation": None,
        "access_levels": [],
        "contains_flyer": False,
        "reply_language": None,
    }


@pytest.fixture()
def resolver_calls(monkeypatch):
    """Every entity resolver call the turn makes (the references route and the assistant service)."""
    from app.api.v1.system import references as references_mod
    from app.services import ai_assistant_service

    calls: list[Any] = []
    for mod in (references_mod, ai_assistant_service):
        real = mod.resolve_references

        def spy(*a, _real=real, **k):
            calls.append(a[1:2])
            return _real(*a, **k)

        monkeypatch.setattr(mod, "resolve_references", spy)
    return calls


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
@pytest.mark.parametrize("settled", [True, False], ids=["contacts_01_02_settled_rows", "contact_30_unsettled_rows"])
def test_round12_an_all_broaden_over_nothing_open_is_one_reset_turn(turn, resolver_calls, settled, gate):
    t = turn(gate)
    stored = _held_subject(settled)
    result = t.say(stored, _measured_all_broaden(gate), "clear all")
    reply = (result.reply or {}).get("text") or ""
    assert reply == ACK["en"], (result.branch_kind, reply)
    assert "every stock" not in reply, reply
    assert "How many units" not in reply, reply
    assert not t.tool_calls, t.tool_calls
    assert not resolver_calls, resolver_calls
    assert not t.casual_calls, "a model was called on a reset turn"
    focus = t.stored_after().get("focus") or {}
    assert not focus.get("tasks"), focus.get("tasks")
    assert not focus.get("products"), focus.get("products")
    _assert_the_reset_turn(t, result, stored)


_STOCK_TOOLS = ["crm_incoming_stock_list", "crm_inventory_stock_balance_list"]

#: Round 12 guards: what each did at b173c6e8c4 (no seam), both paths (measured 22 Oct).
B173_R12 = {
    "show_me_everything_over_a_held_subject": {"lane": "business_query", "actions": ["send_message"], "tools": []},
    "show_all_stock_names_its_domain": {"lane": "business_query", "actions": ["send_message"], "tools": []},
    "the_all_broaden_over_an_open_task": {"lane": "business_query", "actions": ["send_message"], "tools": []},
}


def _r12_guard(name: str, gate: bool) -> tuple[dict[str, Any], dict[str, Any], str]:
    if name == "show_me_everything_over_a_held_subject":
        return _held_subject(), _measured_all_broaden(gate, scope_intent="broaden"), "show me everything"
    if name == "show_all_stock_names_its_domain":
        return _held_subject(), _measured_all_broaden(
            gate, domain_hint="inventory", intent_hint="check_stock", domain_in_message=True), "show all stock"
    return _stored("C28"), _measured_all_broaden(gate), "all"


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
@pytest.mark.parametrize("name", list(B173_R12))
def test_round12_guard_routes_as_at_b173(turn, name, gate):
    t = turn(gate)
    stored, emission, words = _r12_guard(name, gate)
    result = t.say(stored, emission, words)
    assert (result.reply or {}).get("text") != ACK["en"], (result.branch_kind, (result.reply or {}).get("text"))
    assert "reset_turn" not in t.trace_of(result), "the reset seam answered a turn that is no reset"
    assert t.plans, "apply never ran: the turn did not take today's path"
    assert _lane_actions_tools(t, result) == B173_R12[name], _lane_actions_tools(t, result)


# --- round 12b: an all-broaden answering a question the focus holds is no reset ----------------------
#
# Reviewer B1 / S1 on 9f156ca06b: all_broaden_over_nothing_open also fired over the questions the bot
# keeps on the focus rather than as a stored pending (a set clarify, the count question, the
# other-brands offer; the top selling question went with that lane, REPORT-SMART-L R4a), and beside a
# family widening ("all variants").


def _focus_session(focus: Focus) -> dict[str, Any]:
    return {"focus": focus_to_wire(focus), "open_question": None, "ideation": None, "access_levels": [],
            "contains_flyer": False, "reply_language": None}


_WC_KEY = {"domain": "inventory", "set_noun": "water closets", "access_levels": []}

#: The focus-held questions (and a partly listed set), each over the inventory domain.
FOCUS_HELD = {
    "set_clarify": Focus(domains=["inventory"], set_clarify={"kind": "brand", "options": ["Sorento", "Mocha"]}),
    "count_question": Focus(domains=["inventory"], set_page={"set_key": {**_WC_KEY, "total": 9, "shown": 0}}),
    "other_brands_offer": Focus(domains=["inventory"], set_page={"set_key": {
        **_WC_KEY, "total": 5, "shown": 5, "other_brands": [{"brand": "Mocha", "count": 2}]}, "page": 1}),
    "partly_listed_set": Focus(domains=["inventory"], set_page={"set_key": {**_WC_KEY, "total": 9, "shown": 5},
                                                                "page": 1}),
}

#: Each guard's lane, actions and tools at b173c6e8c4 (no seam), both paths (measured 22 Oct).
B173_R12B: dict[str, Any] = {
    **{name: {"lane": "business_query", "actions": ["send_message"], "tools": []} for name in FOCUS_HELD},
    "all_variants_broaden_to": {"lane": "business_query", "actions": ["send_message"], "tools": []},
    "all_variants_family": {"lane": "business_query", "actions": ["send_message"], "tools": _STOCK_TOOLS},
}


def _r12b_guard(name: str, gate: bool) -> tuple[dict[str, Any], dict[str, Any], str]:
    if name in FOCUS_HELD:
        return _focus_session(FOCUS_HELD[name]), _measured_all_broaden(gate, broaden_to=None), "all"
    if name == "all_variants_broaden_to":
        return _held_subject(), _measured_all_broaden(gate, broaden_to="family"), "all variants"
    return _held_subject(), _measured_all_broaden(gate, broaden_to=None, family=True), "the whole family"


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
@pytest.mark.parametrize("name", list(B173_R12B))
def test_round12b_guard_routes_as_at_b173(turn, name, gate):
    t = turn(gate)
    stored, emission, words = _r12b_guard(name, gate)
    result = t.say(stored, emission, words)
    assert (result.reply or {}).get("text") != ACK["en"], (result.branch_kind, (result.reply or {}).get("text"))
    assert "reset_turn" not in t.trace_of(result), "the reset seam answered a turn that is no reset"
    assert _lane_actions_tools(t, result) == B173_R12B[name], _lane_actions_tools(t, result)


# --- round 12c: family false is the exact code alone, no widening -------------------------------------
#
# Reviewer condition on a906aca2f2: `family` is a required parser field (true, false or null); false
# means the exact code alone, so the EVAL-BENCH contacts 01 / 02 read may carry it and is still a reset.


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
def test_round12c_the_all_broaden_with_family_false_over_nothing_open_is_one_reset_turn(turn, resolver_calls, gate):
    t = turn(gate)
    stored = _held_subject()
    result = t.say(stored, _measured_all_broaden(gate, family=False), "clear all")
    reply = (result.reply or {}).get("text") or ""
    assert reply == ACK["en"], (result.branch_kind, reply)
    assert "every stock" not in reply, reply
    assert not t.tool_calls, t.tool_calls
    assert not resolver_calls, resolver_calls
    assert not t.casual_calls, "a model was called on a reset turn"
    _assert_the_reset_turn(t, result, stored)


# --- round 13: a no-pick entity_op clear over an open picker is a reset ----------------------------------
#
# EVAL-BENCH contacts 09 / 10 (c7874eb742): the v63 "clear all" read (business query, topic_reset
# false, mode null, entity_op clear, broaden_axis all, broaden_to all, scope_intent null, no entity,
# no position, no pick) over a stored promotion tier_pick: contact 09 (no domain) re-sent every tier's
# files and kept the question open; contact 10 (the tier question's own promotion domain carried,
# domain_in_message false, a product held) hit "That would search every promotion we have". Measured
# live 22 Oct (x3 each): a real answer to a picker ("all", "semua", "all of them", "1 and 2") always
# carries its picks, a "clear all" never does. Crew ruling (option b): entity_op clear with no answer
# to the open roster (no pick, position or item, mode null or cancel), stating nothing else, is a
# reset; the roster's own domain may ride along when domain_in_message is not true.


def _tier_session(*, held_product: bool) -> dict[str, Any]:
    from app.services.chatbot import answer_bridge

    rows = [{"code": v, "label": label, "value": v} for v, label in
            (("office", "Office"), ("dealer", "Dealer"), ("end_user", "End user"))]
    pending = answer_bridge._tier_options(rows, asked_at_turn=1)
    focus = Focus(products=ht.product_rows("SRTZQ053"), domains=["promotion"]) if held_product else Focus()
    return {"focus": focus_to_wire(focus), "open_question": turn_pending.to_wire(pending), "ideation": None,
            "access_levels": [], "contains_flyer": False, "reply_language": None}


R13_CASES = [("contact_09_no_domain", None, False), ("contact_10_roster_domain_and_a_held_product", "promotion", True)]


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
@pytest.mark.parametrize("name,domain,held", R13_CASES, ids=[c[0] for c in R13_CASES])
def test_round13_a_no_pick_clear_over_the_tier_question_is_one_reset_turn(turn, name, domain, held, gate):
    t = turn(gate)
    stored = _tier_session(held_product=held)
    emission = _measured_all_broaden(gate, **({"domain_hint": domain} if domain else {}))
    result = t.say(stored, emission, "clear all")
    reply = (result.reply or {}).get("text") or ""
    assert reply == ACK["en"], (result.branch_kind, reply)
    assert "every promotion" not in reply, reply
    assert not t.tool_calls, t.tool_calls
    assert t.stored_after().get("open_question") is None, "the tier question stayed open"
    _assert_the_reset_turn(t, result, stored)


def _tier_answer(positions: list[int], gate: bool) -> dict[str, Any]:
    """The measured v63 answer to the tier question: mode pick with the picks, entity_op reuse."""
    emission = _parser_output(
        message_type="business_query", topic_reset=False, entity_op="reuse", broaden_axis=None, scope_intent=None,
        domain_hint="promotion", intent_hint="check_promotion", domain_in_message=False, entities=[],
        reference_positions=list(positions), match_mode=None,
        open_question_answer={"mode": "pick", "picked": list(positions), "items": [], "qty_for_all": None},
    )
    if gate:
        emission["state_changes"] = [{"op": "pick", "axis": None, "position": p} for p in positions]
    return emission


#: Each tier answer at b173c6e8c4 (no seam), both paths (measured 22 Oct).
B173_R13: dict[str, Any] = {
    words: {"lane": "check_promotion", "actions": ["send_message"], "tools": []}
    for words in ("all", "semua", "all of them", "1 and 2")
}


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
@pytest.mark.parametrize("words", list(B173_R13))
def test_round13_guard_a_real_answer_to_the_tier_question_answers_its_picks(turn, words, gate):
    t = turn(gate)
    positions = [1, 2] if words == "1 and 2" else [1, 2, 3]
    result = t.say(_tier_session(held_product=False), _tier_answer(positions, gate), words)
    assert (result.reply or {}).get("text") != ACK["en"], (result.branch_kind, (result.reply or {}).get("text"))
    assert "reset_turn" not in t.trace_of(result), "the reset seam answered a pick"
    assert t.plans, "apply never ran: the pick did not take today's path"
    assert _lane_actions_tools(t, result) == B173_R13[words], _lane_actions_tools(t, result)


# --- round 13 re-pin: two former guards are the measured "clear all" reading -------------------------
#
# Captain OK on #1825 (round 13): the no-pick entity_op clear over a picker is the measured "clear
# all" reading; v63's real "all" answers carry picks (tier 9/9, product picker 9/9). The round 8
# guard "all of them as a broaden alone" and the round 12 guard "the all-broaden over an open picker"
# keep their exact parse and stored picker (C18, an open product_pick) and are resets now.


def _r13_repinned(name: str, gate: bool) -> tuple[dict[str, Any], dict[str, Any], str]:
    if name == "all_of_them_as_a_broaden_alone":
        emission, ops = _read([], domain_hint="inventory", intent_hint="check_stock", entity_op="clear",
                              broaden_axis="all")
        if gate:
            emission["state_changes"] = ops
        return _stored("C18"), emission, "all of them"
    return _stored("C18"), _measured_all_broaden(gate), "all"


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
@pytest.mark.parametrize("name", ["all_of_them_as_a_broaden_alone", "the_all_broaden_over_an_open_picker"])
def test_round13_a_former_guard_no_pick_clear_over_a_picker_is_one_reset_turn(turn, name, gate):
    t = turn(gate)
    stored, emission, words = _r13_repinned(name, gate)
    result = t.say(stored, emission, words)
    assert (result.reply or {}).get("text") == ACK["en"], (result.branch_kind, (result.reply or {}).get("text"))
    assert t.stored_after().get("open_question") is None, "the picker stayed open"
    assert not t.tool_calls, t.tool_calls
    _assert_the_reset_turn(t, result, stored)


# --- round 14: the picker reset reads only the rosters measured on v63 -------------------------------
#
# Reviewer should-fix on round 13: clear_over_an_open_picker covered every roster, but v63 is measured
# (a real "all" answer carries its picks) only for the tier roster and the product roster (did-you-mean
# and stock picks). Captain ruling: limit it to those kinds. An unmeasured roster keeps today's path.

#: The same no-pick entity_op clear read over an open customer_order_pick, at b173c6e8c4 (both paths).
B173_R14_CUSTOMER_ORDER_PICK = {"lane": "business_query", "actions": ["send_message"], "tools": []}


@pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])
def test_round14_guard_a_no_pick_clear_over_an_unmeasured_roster_keeps_todays_path(turn, gate):
    t = turn(gate)
    result = t.say(_stored("C13"), _measured_all_broaden(gate), "clear all")
    assert (result.reply or {}).get("text") != ACK["en"], (result.branch_kind, (result.reply or {}).get("text"))
    assert "reset_turn" not in t.trace_of(result), "the reset seam answered over an unmeasured roster"
    assert t.plans, "apply never ran: the turn did not take today's path"
    assert _lane_actions_tools(t, result) == B173_R14_CUSTOMER_ORDER_PICK, _lane_actions_tools(t, result)
