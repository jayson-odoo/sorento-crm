"""STUCK-QTY-LOOP (owner, 4 Oct 2026): one central rule for every held question.

Live 4 Oct 02:56-03:00: an availability contact's open stock task replayed "How many
units for each? 1. SRTWB1086 - ..." on every message, a low stock report, the switch to
compact and "clear" included. The owner widened the fix to every question or picker the
bot can hold: a held question only captures a reply that answers it, a new intent wins,
a reset clears it, it expires, and an access change drops it.

Plan: documentation/plans/chatbot/PLAN-stuck-qty-loop-04oct.md. The engine replay of the
owner's exact sequence is `test_held_state_engine.py`.
"""
from __future__ import annotations

import dataclasses
import pathlib
import re

import pytest

from app.services.chatbot.lanes.business import low_stock_ask
from app.services.chatbot.turn import held
from app.services.chatbot.turn import pending as pending_mod
from app.services.chatbot.turn.apply import apply
from app.services.chatbot.turn.decide import NEW_ASK, REFINE, decide
from app.services.chatbot.turn.state import Focus, Profile, State, focus_from_wire, focus_to_wire

from tests.chatbot import _ht26_fixtures as ht
from tests.chatbot._turn_helpers import build_policy, entity, verdict

CHATBOT = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "chatbot"

#: The 18 codes the owner's stuck contact was asked about.
SRTWB = [f"SRTWB{n}" for n in range(1086, 1104)]


def _options(n: int = 2) -> list[dict]:
    return [
        {"position": i, "label": f"Option {i}", "code": f"OPT{i}", "entity_type": "product"}
        for i in range(1, n + 1)
    ]


def _pending(kind: str) -> pending_mod.Pending:
    return pending_mod.ask(kind, _options(), asked_at_turn=4, payload={"domain": "order"})


def _state(focus: Focus | None = None, *, pending=None, turn_no: int = 5, access_fp: str | None = "fp-a"):
    return State(
        focus=focus if focus is not None else Focus(),
        pending=pending,
        profile=Profile(access_fp=access_fp),
        turn_no=turn_no,
    )


def _all_held_focus(**over) -> Focus:
    """A focus holding one of every focus-held question at once."""
    base = dict(
        intent="check_stock",
        tasks=(ht.stock_task([(code, None) for code in SRTWB[:3]]),),
        required_ask={"ask": "low_stock_report", "values": {}, "asking": "category"},
        set_page={"set_key": "k"},
        set_clarify={"term": "tap", "options": ["tap", "wash basin"], "ask": "x"},
        top_selling={"rank_by": "qty", "asked": "metric", "who": {"x": 1}, "unclear": "y"},
        held_turn=4,
        held_access="fp-a",
    )
    base.update(over)
    return Focus(**base)


def _nothing_held(state: State) -> bool:
    return not held.held_slots(state)


# --------------------------------------------------------------------------- #
# The registry: nothing that can hold a question escapes the central rule
# --------------------------------------------------------------------------- #


def test_every_focus_field_is_classified_held_or_subject():
    """A new Focus field must be named in `held.FOCUS_HELD` (the central rule clears it)
    or `held.FOCUS_NOT_HELD` (it holds no question). Unclassified fails here."""
    names = {f.name for f in dataclasses.fields(Focus)}
    classified = set(held.FOCUS_HELD) | set(held.FOCUS_NOT_HELD)
    assert not (set(held.FOCUS_HELD) & set(held.FOCUS_NOT_HELD))
    assert names == classified, f"unclassified: {sorted(names - classified)}, stale: {sorted(classified - names)}"


def test_every_state_field_is_classified_held_or_subject():
    names = {f.name for f in dataclasses.fields(State)}
    classified = set(held.STATE_HELD) | set(held.STATE_NOT_HELD)
    assert names == classified, f"unclassified: {sorted(names - classified)}"


def test_every_held_slot_has_a_clearer_in_the_registry():
    assert set(held.SLOTS) == {f"focus.{n}" for n in held.FOCUS_HELD} | {f"state.{n}" for n in held.STATE_HELD}


def test_every_minted_pending_kind_is_registered():
    """Every `ask("<kind>", ...)` literal in the chatbot package is a kind the central rule
    knows: in PENDING_KINDS, or a narrower-minted roster (`*_pick` / `*_ask`)."""
    minted: set[str] = set()
    for path in CHATBOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        minted |= set(re.findall(r"\bask\(\s*[\"']([a-z_]+)[\"']", text))
        minted |= set(re.findall(r"\bPending\(\s*kind=[\"']([a-z_]+)[\"']", text))
    assert minted, "the scan found no mint site at all"
    unknown = {k for k in minted if k not in pending_mod.PENDING_KINDS and not pending_mod.is_roster(k)}
    assert not unknown, f"pending kinds minted outside the registry: {sorted(unknown)}"


# --------------------------------------------------------------------------- #
# The matrix: every pending kind x every rule
# --------------------------------------------------------------------------- #

KINDS = [*pending_mod.PENDING_KINDS, "brand_pick", "attachment_type_ask", "form_pick"]


@pytest.mark.parametrize("kind", KINDS)
def test_a_new_intent_drops_the_open_question(kind):
    state = _state(Focus(intent="check_order", domains=["order"]), pending=_pending(kind))
    v = verdict(
        intent_hint="check_promotion",
        domain_hint="promotion",
        entities=[entity("SRT5674")],
    )
    out, why = held.consume(state, v)
    assert out.pending is None
    assert why == "new_intent"


@pytest.mark.parametrize("kind", KINDS)
def test_a_reset_drops_the_open_question(kind):
    state = _state(Focus(intent="check_order"), pending=_pending(kind))
    out, why = held.consume(state, verdict(topic_reset=True))
    assert out.pending is None
    assert why == "topic_reset"


@pytest.mark.parametrize("kind", KINDS)
def test_the_open_question_expires(kind):
    state = _state(Focus(intent="check_order", held_turn=4, held_access="fp-a"), pending=_pending(kind), turn_no=4 + held.HELD_TTL_TURNS + 1)
    out, why = held.expire(state)
    assert out.pending is None
    assert why == "ttl"


@pytest.mark.parametrize("kind", KINDS)
def test_the_open_question_survives_inside_its_ttl(kind):
    state = _state(Focus(intent="check_order", held_turn=4, held_access="fp-a"), pending=_pending(kind), turn_no=4 + held.HELD_TTL_TURNS)
    out, why = held.expire(state)
    assert out.pending is not None
    assert why is None


@pytest.mark.parametrize("kind", KINDS)
def test_an_access_change_drops_the_open_question(kind):
    state = _state(Focus(intent="check_order", held_turn=4, held_access="fp-old"), pending=_pending(kind), access_fp="fp-new")
    out, why = held.expire(state)
    assert out.pending is None
    assert why == "access_changed"


@pytest.mark.parametrize("kind", KINDS)
def test_a_genuine_answer_keeps_the_open_question(kind):
    """A position picked off the question is an answer whatever intent the parser put on
    it ("2 stock" picks row 2), so the question is the arm's to settle, not dropped."""
    state = _state(Focus(intent="check_order"), pending=_pending(kind))
    v = verdict(intent_hint="check_stock", domain_hint="inventory", reference_positions=[2])
    out, why = held.consume(state, v)
    assert out.pending is not None
    assert why is None


@pytest.mark.parametrize("kind", KINDS)
def test_the_same_intent_keeps_the_open_question(kind):
    state = _state(Focus(intent="check_order"), pending=_pending(kind))
    out, why = held.consume(state, verdict(intent_hint="check_order", entities=[entity("7445")]))
    assert out.pending is not None
    assert why is None


@pytest.mark.parametrize("kind", KINDS)
def test_no_intent_keeps_the_open_question(kind):
    """A message the parser gave no intent says nothing about a new question."""
    state = _state(Focus(intent="check_order"), pending=_pending(kind))
    out, why = held.consume(state, verdict(intent_hint=None))
    assert out.pending is not None


# Every focus-held slot, the same rules.


@pytest.mark.parametrize("slot", sorted(held.FOCUS_HELD))
def test_a_new_intent_drops_every_focus_held_question(slot):
    out, why = held.consume(_state(_all_held_focus()), verdict(intent_hint="check_promotion", entities=[entity("X1")]))
    assert why == "new_intent"
    assert f"focus.{slot}" not in held.held_slots(out)


def test_a_reset_drops_everything_held():
    out, why = held.consume(_state(_all_held_focus(), pending=_pending("customer_pick")), verdict(topic_reset=True))
    assert why == "topic_reset"
    assert _nothing_held(out)


def test_ttl_and_access_drop_everything_held():
    ttl, why = held.expire(_state(_all_held_focus(held_turn=1), pending=_pending("team_pick"), turn_no=1 + held.HELD_TTL_TURNS + 1))
    assert why == "ttl" and _nothing_held(ttl)
    acc, why = held.expire(_state(_all_held_focus(held_access="fp-old"), pending=_pending("team_pick"), access_fp="fp-new"))
    assert why == "access_changed" and _nothing_held(acc)


def test_an_unstamped_held_state_is_kept_not_dropped():
    """Rows written before this lane carry no stamp: they are judged on their next turn
    (and stamped then), never dropped wholesale on deploy."""
    state = _state(_all_held_focus(held_turn=None, held_access=None), pending=_pending("customer_pick"))
    out, why = held.expire(state)
    assert why is None
    assert out.pending is not None


def test_a_held_stock_quantity_keeps_the_task_under_another_intent():
    """A quantity the stock task claims is an answer, whatever intent rides on it."""
    focus = _all_held_focus()
    out, why = held.consume(_state(focus), verdict(intent_hint="check_incoming", demand_qty=10))
    assert why is None
    assert out.focus.tasks


# --------------------------------------------------------------------------- #
# The stamp
# --------------------------------------------------------------------------- #


def test_stamp_records_turn_and_access_when_held_state_changed():
    before = focus_to_wire(Focus())
    after = _state(_all_held_focus(held_turn=None, held_access=None), turn_no=9, access_fp="fp-z")
    stamped = held.stamp(after, {"focus": before, "open_question": None})
    assert (stamped.focus.held_turn, stamped.focus.held_access) == (9, "fp-z")


def test_stamp_carries_an_unchanged_held_state():
    focus = _all_held_focus(held_turn=3, held_access="fp-a")
    before = {"focus": focus_to_wire(focus), "open_question": None}
    stamped = held.stamp(_state(focus, turn_no=7, access_fp="fp-a"), before)
    assert stamped.focus.held_turn == 3


def test_stamp_clears_when_nothing_is_held():
    stamped = held.stamp(_state(Focus(held_turn=3, held_access="fp-a"), turn_no=7), {"focus": None, "open_question": None})
    assert (stamped.focus.held_turn, stamped.focus.held_access) == (None, None)


def test_the_stamp_and_intent_survive_the_wire():
    focus = focus_from_wire(focus_to_wire(Focus(intent="check_stock", held_turn=3, held_access="fp-a")))
    assert (focus.intent, focus.held_turn, focus.held_access) == ("check_stock", 3, "fp-a")


def test_consume_records_the_message_intent_on_the_focus():
    out, _ = held.consume(_state(Focus(intent="check_order")), verdict(intent_hint="check_stock"))
    assert out.focus.intent == "check_stock"
    out, _ = held.consume(_state(Focus(intent="check_order")), verdict(intent_hint=None))
    assert out.focus.intent == "check_order"


# --------------------------------------------------------------------------- #
# The stuck loop itself (task.run's RESUME arm)
# --------------------------------------------------------------------------- #


def _stuck_focus() -> Focus:
    return Focus(
        tasks=(ht.stock_task([(code, None) for code in SRTWB]),),
        domains=["inventory"],
    )


def _low_stock_verdict() -> dict:
    v = verdict(
        intent_hint="low_stock_report",
        domain_hint="inventory",
        entities=[
            entity("Sorento", hint="brand"),
            entity("water tap", hint="category"),
        ],
    )
    return low_stock_ask.take_words(v, "low stock report for sorento water tap")


def test_a_low_stock_report_never_replays_the_quantity_question():
    """The owner's exact turn: the low stock verdict reaches the task step with no
    entities (take_words moved them), and the stored question came back verbatim."""
    _state2, plan = apply(ht.state(_stuck_focus()), _low_stock_verdict(), build_policy())
    assert plan.trace.task_question is None
    assert "task_resumed_stock_qty" not in plan.trace.rules_fired


def test_clear_without_a_reset_flag_never_replays_the_quantity_question():
    """"clear" the parser gave no intent and no topic_reset: nothing asked to resume."""
    _state2, plan = apply(ht.state(_stuck_focus()), verdict(domain_hint="inventory", entities=[]), build_policy())
    assert plan.trace.task_question is None


def test_clear_as_a_reset_ends_the_task():
    state, why = held.consume(_state(_stuck_focus()), verdict(topic_reset=True, domain_hint=None))
    assert why == "topic_reset"
    assert state.focus.tasks == ()


def test_back_to_the_stock_check_still_resumes():
    """The prompt's own resume signal ("back to the stock check": check_stock, no
    entities) still asks what is owed: the resume needs an explicit signal, not none."""
    _state2, plan = apply(
        ht.state(_stuck_focus()),
        verdict(domain_hint="inventory", intent_hint="check_stock", entities=[]),
        build_policy(),
    )
    assert "task_resumed_stock_qty" in plan.trace.rules_fired
    assert plan.trace.task_question.startswith("How many units for each?")


def test_the_owner_sequence_through_the_central_rule():
    """Availability task open, then the low stock ask: the central rule drops the task
    (a new intent that answers nothing) before the task step ever runs."""
    state = _state(dataclasses.replace(_stuck_focus(), intent="check_stock"))
    state, why = held.consume(state, _low_stock_verdict())
    assert why == "new_intent"
    assert state.focus.tasks == ()


# --------------------------------------------------------------------------- #
# Crew report 2: a refine under a different intent is a fresh ask
# --------------------------------------------------------------------------- #


def test_a_refine_under_a_new_intent_is_a_new_ask_that_starts_fresh():
    v = verdict(intent_hint="check_stock", domain_in_message=False, entities=[entity("taiyang", hint="brand")])
    assert decide(v, Focus(intent="top_selling")).kind == REFINE  # no marker: the old reading
    marked = dict(v)
    held.consume(_state(Focus(intent="top_selling")), marked)
    assert marked.get(held.NEW_INTENT) is True  # consume marks the verdict it read
    d = decide({**v, held.NEW_INTENT: True}, Focus(intent="check_stock"))
    assert d.kind == NEW_ASK
    assert d.starts_fresh


def test_carried_entities_of_the_old_intent_do_not_reach_a_new_intent():
    """'taiyang only' after a ranking by sales agent William: William is the old ask's
    and must not be resolved (and missed) as part of the stock ask."""
    focus = Focus(
        intent="top_selling",
        domains=["sales"],
        extra={"sales_agent": [entity("William", hint="sales_agent")]},
    )
    v = verdict(intent_hint="check_stock", domain_hint="inventory", domain_in_message=False, entities=[entity("taiyang", hint="brand")])
    state, why = held.consume(_state(focus), v)
    assert why is None or why == "new_intent"
    out, _plan = apply(state, v, build_policy())
    assert not out.focus.extra.get("sales_agent")


def test_anaphora_under_a_new_intent_still_refines():
    """"did golden win deliver these?" points at the carried products on purpose."""
    v = verdict(
        intent_hint="check_order",
        domain_in_message=True,
        entities=[entity("golden win", hint="customer")],
        anaphora={"backward_reference": True},
    )
    d = decide({**v, held.NEW_INTENT: True}, Focus(intent="check_stock"))
    assert d.kind == REFINE


# --------------------------------------------------------------------------- #
# Crew report 2, item 1: a lane's own question outranks the resolver's miss
# --------------------------------------------------------------------------- #


def test_a_lane_question_is_never_turned_into_a_not_found():
    from app.services.chatbot import answer_bridge

    envelope = {"required_ask": {"ask": "low_stock_report", "asking": "category"}, "raw_fragment": {"kind": "result", "fetch": {}}}
    assert answer_bridge.answers_a_miss({"_exit_kind": "not_found"}, envelope) is False
    plain = {"raw_fragment": {"kind": "result", "fetch": {}}}
    assert answer_bridge.answers_a_miss({"_exit_kind": "not_found"}, plain) is True
