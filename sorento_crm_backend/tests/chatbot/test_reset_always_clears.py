"""CHAT-PICK-QTY-STATE release gate (#1829): "clear all" is ONE reset, on both paths.

EVAL-BENCH replayed "clear all" over stored sessions: main 552858f168 reset in 12 of 12 runs,
the release build declined an escalation offer, kept or re-asked a stock task, or refused an
empty stock fetch ("That would search every stock we have ...").

Crew ruling (binding):
1. One reset predicate, read once at the top of `apply`: `topic_reset` true, or an
   `open_question_answer` cancel that names nothing (no entity, no position, no pick, no item
   with a quantity). Mode "no" is a decline, never a reset.
2. On a reset the stored question closes unanswered (no accept, no decline, no pick), every task
   closes (open and parked, whatever domain is named) and the stored list goes.
3. A reset that names nothing fetches nothing and asks nothing: the plan main gives the reset
   (no fetch, no ask, no task question, the small-talk lane), never the empty-fetch refusal.
4. A reset that names its own ask still plans that ask, after the clear.

The verdicts are the parsers' own reads of "clear all", measured live on synthetic contexts.
v63 (old path): entity_op clear, broaden_axis all, nothing named, no domain_hint, no
state_changes; topic_reset true with mode cancel or null, or topic_reset false with mode cancel.
v92 (state path): (a) topic_reset false, cancel, [close_question], inventory; (b) topic_reset
false, cancel, [answer], promotion; (c) topic_reset true, [new_subject, clear product,
close_question] or [close_question, new_subject], a domain_hint; (d) topic_reset true, [clear
customer, clear period], entity_op clear, broaden_axis all. Synthetic codes and contacts only.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from app.services.chatbot.turn import chat_state
from app.services.chatbot.turn import pending as turn_pending
from app.services.chatbot.turn import question as question_mod
from app.services.chatbot.turn.apply import apply
from app.services.chatbot.turn.route import route
from app.services.chatbot.turn.state import Focus

from tests.chatbot import _ht26_fixtures as ht
from tests.chatbot._turn_helpers import build_policy, verdict

DOMAINS = ["inventory", "incoming", "order", "sales", "product_attachment", "promotion"]
KINDS = ["product", "customer", "brand", "promotion", "attachment", "order"]

TWENTY = [f"SRTZQ{i:03d}" for i in range(1, 21)]
FOUR = ["SRTZA101", "SRTZA102", "SRTZA103", "SRTZA104"]
TWO = ["SRTZB201", "SRTZB202"]
OTHER = ["SRTZC301", "SRTZC302", "SRTZC303"]

#: What a stored question answered, accepted or declined leaves on the trace.
ANSWER_RULES = {
    "answer_pending",
    "answer_pending_accept",
    "answer_pending_decline",
    "answer_pending_unresolved",
    "stock_pick_declined",
    "stock_pick_yes",
    "escalation_product_picked",
    "offer_hold",
}
ANSWER_LANES = {"escalation", "escalation_declined", "offer_declined", "offer_hold", "escalation_barred"}


# --- the stored sessions --------------------------------------------------------------------------


def _rows(codes, shown_at_turn=4):
    return [
        {"position": i, "label": c, "code": c, "uuid": ht.uuid_of(c), "entity_type": "product",
         "shown_at_turn": shown_at_turn}
        for i, c in enumerate(codes, 1)
    ]


def _offer():
    """The one-option escalation offer: "Would you like me to check with the warehouse?"."""
    return turn_pending.ask(
        "team_pick", [{"position": 1, "label": "Yes", "entity_type": "team", "payload": {}}],
        team="warehouse", asked_at_turn=4, expects="yes_no",
    )


def _tier_pick():
    return turn_pending.ask(
        "tier_pick",
        [
            {"position": i, "label": t.replace("_", " "), "code": t, "uuid": t, "uuids": [t],
             "entity_type": "tier", "payload": {"tier": t}}
            for i, t in enumerate(["dealer", "office", "end_user"], 1)
        ],
        asked_at_turn=4, expects="pick", payload={"domain": "promotion", "domains": ["promotion"]},
    )


def _customer():
    return {"raw": "ZZC001", "hint": "customer", "canonical_code": "ZZC001", "uuid": ht.uuid_of("ZZC001"),
            "current_message": False, "confident": True}


def _session(context: str, gate: bool):
    """`gate` is the state path: the list the last reply showed is stored there only."""
    pending = None
    if context == "offer_and_parked_task":  # C04
        tasks = (ht.stock_task([(c, None) for c in TWENTY], status="parked", opened_at_turn=1, touched_at_turn=2),)
        focus = Focus(products=ht.product_rows(TWENTY[0]), domains=["inventory"], tasks=tasks)
        shown, pending = TWENTY, _offer()
    elif context in ("open_task_and_another", "open_two_line_task_and_another"):  # C28, C30
        codes = FOUR if context == "open_task_and_another" else TWO
        tasks = (
            ht.stock_task([(c, None) for c in codes], status="open", opened_at_turn=3, touched_at_turn=4),
            ht.stock_task([(c, None) for c in OTHER], status="parked", opened_at_turn=1, touched_at_turn=1),
        )
        focus = Focus(products=ht.product_rows(*codes), domains=["inventory"], tasks=tasks)
        shown = codes
    elif context == "offer_with_a_held_customer":  # C03
        focus = Focus(customers=[_customer()], products=ht.product_rows(TWENTY[0]), domains=["inventory"])
        shown, pending = [TWENTY[0]], _offer()
    elif context == "offer":  # C01, C02
        focus = Focus(products=ht.product_rows(TWENTY[0]), domains=["inventory"])
        shown, pending = [TWENTY[0]], _offer()
    elif context == "tier_pick":
        focus = Focus(products=ht.product_rows(TWENTY[0]), domains=["promotion"])
        shown, pending = TWENTY[:3], _tier_pick()
    elif context == "quantities_question":
        tasks = (ht.stock_task([(c, None) for c in FOUR], status="open", opened_at_turn=3, touched_at_turn=4),)
        focus = Focus(products=ht.product_rows(*FOUR), domains=["inventory"], tasks=tasks)
        shown = FOUR
    else:
        raise KeyError(context)
    focus = replace(focus, last_list=_rows(shown) if gate else None)
    return replace(ht.state(focus, pending=pending, turn_no=5), state_path=gate)


# --- the parses of "clear all" ----------------------------------------------------------------------


def _answer(mode):
    return {"mode": mode, "picked": [], "items": [], "qty_for_all": None}


def _op(op, axis=None):
    return {"op": op, "axis": axis, "position": None}


V63 = {
    "v63_reset_cancel": dict(topic_reset=True, mode="cancel"),
    "v63_reset": dict(topic_reset=True, mode=None),
    "v63_cancel": dict(topic_reset=False, mode="cancel"),
}
V92 = {
    "v92_close": dict(topic_reset=False, mode="cancel", domain_hint="inventory", intent_hint="check_stock",
                      changes=[_op("close_question")]),
    "v92_answer": dict(topic_reset=False, mode="cancel", domain_hint="promotion", changes=[_op("answer")]),
    "v92_new_subject": dict(topic_reset=True, mode=None, domain_hint="inventory", intent_hint="check_stock",
                            changes=[_op("new_subject"), _op("clear", "product"), _op("close_question")]),
    # A domain the held tasks are not about: the reset still closes them.
    "v92_close_new_subject": dict(topic_reset=True, mode="cancel", domain_hint="promotion",
                                  changes=[_op("close_question"), _op("new_subject")]),
    "v92_clear_slots": dict(topic_reset=True, mode=None, entity_op="clear", broaden_axis="all",
                            changes=[_op("clear", "customer"), _op("clear", "period")]),
    # Reviewer B1: a cancel beside ops other than a lone close_question. The state applier
    # strips the answer of a turn its ops do not answer, so the reset is read before it runs.
    "v92_clear_product_close": dict(topic_reset=False, mode="cancel", domain_hint="inventory",
                                    intent_hint="check_stock",
                                    changes=[_op("clear", "product"), _op("close_question")]),
    "v92_clear_product": dict(topic_reset=False, mode="cancel", domain_hint="inventory",
                              intent_hint="check_stock", changes=[_op("clear", "product")]),
    "v92_clear_slots_cancel": dict(topic_reset=False, mode="cancel", domain_hint="inventory",
                                   intent_hint="check_stock",
                                   changes=[_op("clear", "customer"), _op("clear", "period")]),
    "v92_new_subject_clear_customer": dict(topic_reset=False, mode="cancel", domain_hint="inventory",
                                           intent_hint="check_stock",
                                           changes=[_op("new_subject"), _op("clear", "customer")]),
}


def _clear_all(shape: str):
    if shape in V63:
        spec = V63[shape]
        return verdict(entity_op="clear", broaden_axis="all", entities=[], reference_positions=[],
                       topic_reset=spec["topic_reset"], open_question_answer=_answer(spec["mode"]))
    spec = dict(V92[shape])
    changes = spec.pop("changes")
    mode = spec.pop("mode")
    v = verdict(entities=[], reference_positions=[], open_question_answer=_answer(mode), **spec)
    v["state_changes"] = changes
    return v


def _cases(state_shapes):
    """Both gates: the old path reads the v63 parses, the state path the v92 ones."""
    return pytest.mark.parametrize(
        "gate,shape",
        [(False, s) for s in V63] + [(True, s) for s in state_shapes],
        ids=[f"old_path-{s}" for s in V63] + [f"state_path-{s}" for s in state_shapes],
    )


CANCEL_BESIDE_OTHER_OPS = [
    "v92_clear_product_close", "v92_clear_product", "v92_clear_slots_cancel", "v92_new_subject_clear_customer",
]
ON_A_TASK_OR_OFFER = [
    "v92_close", "v92_new_subject", "v92_close_new_subject", "v92_clear_slots", "v92_answer",
    *CANCEL_BESIDE_OTHER_OPS,
]
ON_A_TIER_PICK = [
    "v92_answer", "v92_new_subject", "v92_close_new_subject", "v92_clear_slots", *CANCEL_BESIDE_OTHER_OPS,
]


def _turn(state, v):
    if v.get("state_changes") is not None:
        applied = chat_state.apply_changes(
            state, v, open_question=question_mod.open_question(state.pending, state.focus.tasks),
            domains=DOMAINS, kinds=KINDS, brands=[], positions_read_elsewhere=False,
        )
        assert applied.state.state_gate, "the state path was not entered"
        state, v = applied.state, applied.verdict
    return apply(state, v, build_policy())


def _assert_the_reset(new_state, plan):
    rules = list(plan.trace.rules_fired)
    # Rule 2: the stored question closes and is never answered.
    assert new_state.pending is None, new_state.pending
    assert question_mod.open_question(new_state.pending, new_state.focus.tasks) is None
    assert plan.trace.lane not in ANSWER_LANES, (plan.trace.lane, rules)
    answered = [r for r in rules if r in ANSWER_RULES or r.startswith("open_question_answer_")]
    assert not answered, ("the stored question was answered", answered)
    # Rule 2: every task closes, the open one and the parked one, and the stored list goes.
    assert not new_state.focus.tasks, [(t.status, [s.label for s in t.slots][:3]) for t in new_state.focus.tasks]
    assert not new_state.focus.last_list, "the stored list survived the reset"
    # Rule 3: main's reset plan. The empty-fetch refusal never fires, nothing is fetched or asked.
    assert "refused_empty_subject" not in rules, rules
    assert plan.fetch == [], [(s.domain, [e.get("canonical_code") for e in s.entities]) for s in plan.fetch]
    assert plan.ask is None, plan.ask
    assert plan.trace.task_question is None, plan.trace.task_question
    assert not plan.denied
    assert route(plan) == "low_signal", (route(plan), plan.domains, rules)


# --- C04: an escalation offer over a parked stock task ----------------------------------------------


@_cases(ON_A_TASK_OR_OFFER)
def test_clear_all_over_an_offer_and_a_parked_task_is_a_reset(gate, shape):
    _assert_the_reset(*_turn(_session("offer_and_parked_task", gate), _clear_all(shape)))


# --- C28 / C30: an open stock task, a different task held beside it ---------------------------------


@_cases(ON_A_TASK_OR_OFFER)
def test_clear_all_over_an_open_task_and_another_task_is_a_reset(gate, shape):
    _assert_the_reset(*_turn(_session("open_task_and_another", gate), _clear_all(shape)))


@_cases(ON_A_TASK_OR_OFFER)
def test_clear_all_over_an_open_two_line_task_and_another_task_is_a_reset(gate, shape):
    _assert_the_reset(*_turn(_session("open_two_line_task_and_another", gate), _clear_all(shape)))


# --- C03 / C01 / C02: an open escalation offer -------------------------------------------------------


@_cases(ON_A_TASK_OR_OFFER)
def test_clear_all_over_an_offer_with_a_held_customer_is_a_reset(gate, shape):
    _assert_the_reset(*_turn(_session("offer_with_a_held_customer", gate), _clear_all(shape)))


@_cases(ON_A_TASK_OR_OFFER)
def test_clear_all_over_an_offer_is_a_reset(gate, shape):
    _assert_the_reset(*_turn(_session("offer", gate), _clear_all(shape)))


# --- v92 (a) / (b): a tier pick, and the open quantities question -----------------------------------


@_cases(ON_A_TIER_PICK)
def test_clear_all_over_a_tier_pick_is_a_reset(gate, shape):
    _assert_the_reset(*_turn(_session("tier_pick", gate), _clear_all(shape)))


@_cases(ON_A_TASK_OR_OFFER)
def test_clear_all_over_the_open_quantities_question_is_a_reset(gate, shape):
    _assert_the_reset(*_turn(_session("quantities_question", gate), _clear_all(shape)))


# --- guards -----------------------------------------------------------------------------------------

GATES = pytest.mark.parametrize("gate", [False, True], ids=["old_path", "state_path"])


@GATES
@pytest.mark.parametrize("context", ["offer", "open_task_and_another"])
def test_guard_a_reset_that_names_a_product_still_fetches_that_product(gate, context):
    """Rule 4: "clear all, check stock ZZP999" clears, then asks about ZZP999 alone."""
    typed = {"raw": "ZZP999", "hint": "product", "canonical_code": "ZZP999", "uuid": ht.uuid_of("ZZP999"),
             "current_message": True, "confident": True, "hint_confident": True}
    v = verdict(domain_hint="inventory", intent_hint="check_stock", entities=[typed], entity_op="replace",
                topic_reset=True, open_question_answer=_answer(None))
    if gate:
        v["state_changes"] = [_op("new_subject"), _op("set", "product")]
    new_state, plan = _turn(_session(context, gate), v)
    assert new_state.pending is None, new_state.pending
    assert not new_state.focus.tasks, new_state.focus.tasks
    assert not new_state.focus.last_list
    assert plan.trace.lane not in ANSWER_LANES, plan.trace.lane
    codes = [[e.get("canonical_code") for e in spec.entities] for spec in plan.fetch]
    assert [s.domain for s in plan.fetch] == ["inventory"] and codes == [["ZZP999"]], (codes, plan.trace.rules_fired)


@GATES
def test_guard_a_no_over_an_offer_is_still_a_decline(gate):
    """Mode "no" is the offer's decline, never a reset: "Escalation declined." as today."""
    v = verdict(domain_hint="inventory", intent_hint="check_stock", entities=[], topic_reset=False,
                is_affirmative=False, open_question_answer=_answer("no"))
    if gate:
        v["state_changes"] = [_op("answer")]
    new_state, plan = _turn(_session("offer", gate), v)
    assert plan.trace.lane == "escalation_declined", (plan.trace.lane, plan.trace.rules_fired)
    assert "answer_pending_decline" in plan.trace.rules_fired
    assert new_state.pending is None


# --- round 3 (reviewer S1 to S4b) ---------------------------------------------------------------------

#: One reset read per gate: the v63 cancel on the old path, the v92 close on the state path.
RESET_READ = {False: "v63_cancel", True: "v92_close"}


@GATES
@pytest.mark.parametrize("context", ["offer_and_parked_task", "offer_with_a_held_customer"])
@pytest.mark.parametrize("flag", ["escalation_declined", "is_escalation_confirmation"])
def test_a_reset_over_an_offer_reads_no_escalation_flag(gate, context, flag):
    """S1: the parser's escalation flags ride on a reset parse too; the offer closes unanswered,
    so neither "Escalation declined." nor a hand-over comes of them."""
    v = _clear_all(RESET_READ[gate])
    v["escalation"] = {**(v.get("escalation") or {}), flag: True}
    v["is_affirmative"] = flag == "is_escalation_confirmation"
    _assert_the_reset(*_turn(_session(context, gate), v))


def _echo(code):
    """The parser's echo of a held row: `current_message` false, so this message names nothing."""
    return {"raw": code, "hint": "product", "canonical_code": code, "uuid": ht.uuid_of(code),
            "current_message": False, "confident": True}


@GATES
@pytest.mark.parametrize("shape", ["cancel", "reset"])
def test_an_echo_of_a_held_line_names_nothing_and_the_reset_fetches_nothing(gate, shape):
    """S2: a carried echo (`current_message` false) is not naming. A cancel beside one is a reset,
    and a reset never writes the echo back to fetch it."""
    if gate:
        v = _clear_all("v92_close" if shape == "cancel" else "v92_new_subject")
    else:
        v = _clear_all("v63_cancel" if shape == "cancel" else "v63_reset")
    v["entities"] = [_echo(TWENTY[4])]
    new_state, plan = _turn(_session("offer_and_parked_task", gate), v)
    _assert_the_reset(new_state, plan)
    held = [p.get("canonical_code") for p in new_state.focus.products]
    assert TWENTY[4] not in held, ("the echo was written back to be fetched next", held)


@GATES
def test_a_cancel_naming_a_line_of_the_open_quantities_question_is_a_reset(gate):
    """S4b ("batal SRTZA102"): an entity that is one of the open question's own lines names
    nothing new; the cancel resets and the line is dropped, never fetched or asked."""
    typed = {"raw": FOUR[1], "hint": "product", "canonical_code": FOUR[1], "current_message": True,
             "confident": True, "hint_confident": True}
    v = _clear_all(RESET_READ[gate])
    v["entities"] = [typed]
    _assert_the_reset(*_turn(_session("quantities_question", gate), v))


@GATES
def test_guard_a_cancel_naming_a_product_off_the_open_question_is_not_a_reset(gate):
    """S4b's other half (rule 4, fix 7): a product the question does not list is a new ask."""
    typed = {"raw": "ZZP999", "hint": "product", "canonical_code": "ZZP999", "uuid": ht.uuid_of("ZZP999"),
             "current_message": True, "confident": True, "hint_confident": True}
    v = _clear_all(RESET_READ[gate])
    v["entities"] = [typed]
    _new_state, plan = _turn(_session("quantities_question", gate), v)
    codes = [e.get("canonical_code") for spec in plan.fetch for e in spec.entities]
    assert "ZZP999" in codes, (codes, plan.trace.rules_fired)


@GATES
@pytest.mark.parametrize("context", ["offer_with_a_held_customer", "offer"])
def test_a_reset_naming_nothing_wipes_what_was_held_and_the_next_stock_ask_fetches_none_of_it(gate, context):
    """S3: whatever the mode, a reset naming nothing leaves nothing held (only the tier and the
    brands, as the old path's wipe), so a following "stock?" fetches no held customer or product."""
    shapes = ("v63_reset", "v63_cancel") if not gate else ("v92_new_subject", "v92_clear_slots")
    for shape in shapes:
        new_state, plan = _turn(_session(context, gate), _clear_all(shape))
        _assert_the_reset(new_state, plan)
        assert new_state.focus.customers == [], (shape, new_state.focus.customers)
        assert new_state.focus.products == [], (shape, new_state.focus.products)
        follow = verdict(domain_hint="inventory", intent_hint="check_stock", entities=[])
        if gate:
            # After a full reset nothing is shown, so the applier runs its first-ask path (no
            # state gate, by design): the follow-up goes through it without `_turn`'s gate check.
            follow["state_changes"] = []
            applied = chat_state.apply_changes(
                new_state, follow, open_question=question_mod.open_question(new_state.pending, new_state.focus.tasks),
                domains=DOMAINS, kinds=KINDS, brands=[], positions_read_elsewhere=False,
            )
            _after, plan2 = apply(applied.state, applied.verdict, build_policy())
        else:
            _after, plan2 = _turn(new_state, follow)
        held = {"ZZC001", TWENTY[0]}
        fetched = {e.get("canonical_code") for spec in plan2.fetch for e in spec.entities}
        assert not fetched & held, (shape, fetched)


def test_a_reset_that_closes_a_stock_check_drops_the_products_it_was_about():
    """The stock-check product clear inside the reset, on its own: a state-path reset that names a
    brand of its own (so no wipe runs) still leaves none of the closed check's products held."""
    tasks = (ht.stock_task([(c, None) for c in FOUR], status="open", opened_at_turn=3, touched_at_turn=4),)
    focus = Focus(customers=[_customer()], products=ht.product_rows(*FOUR), domains=["inventory"], tasks=tasks)
    state = replace(ht.state(focus, turn_no=5), state_path=True)
    brand = {"raw": "mocha", "hint": "brand", "canonical_code": "MOCHA", "current_message": True, "confident": True}
    v = verdict(entities=[brand], topic_reset=True, open_question_answer=_answer(None))
    v["state_changes"] = [_op("clear", "customer")]
    new_state, plan = _turn(state, v)
    assert not new_state.focus.tasks, new_state.focus.tasks
    assert new_state.focus.products == [], new_state.focus.products
    assert "task_close_clears_products" in plan.trace.rules_fired, plan.trace.rules_fired
