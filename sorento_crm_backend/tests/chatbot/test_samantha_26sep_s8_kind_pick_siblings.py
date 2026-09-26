"""Phase 2 RED tests - issue #1262 (Samantha case), slice 8, finding F1b (siblings).

Turn T3: Samantha names "Sorento" (ambiguous - customer or transporter) and "Cheng
Huat Sentul" (resolved cleanly to one customer) in the same message. `turn/reconcile.
py`'s two-kind-hit branch arms a `kind_pick` for "Sorento", and `turn/apply.py`'s
`_reconcile_step` short-circuits the WHOLE turn on any kind pick - returning the INPUT
`state` unchanged (apply.py:1535-1536) - so Cheng Huat Sentul, which had resolved
perfectly, is thrown away along with the ambiguous word.

AC-S8-1: the pick is asked AND `focus.customers` keeps Cheng Huat Sentul.
AC-S8-2: two ambiguous tokens in one message - the first is asked, the second is not
lost, and it is asked once the first pick is answered.

Plan: PLAN-chatbot-samantha-slices-26sep.md, slice 8. UAC:
chatbot-samantha-slices-26sep-acceptance-criteria.md.
"""
from __future__ import annotations

from tests.chatbot._turn_helpers import build_policy, entity, verdict

CHENG_HUAT_UUID = "b5a1c9de-3f2a-4c1b-9e7d-2a6f8c0d4e5b"


def test_t3_kind_pick_keeps_cheng_huat_sentul():
    """AC-S8-1. `resolved` carries BOTH tokens' hit counts: "Sorento" hits two kinds
    (arms the pick), "Cheng Huat Sentul" hits exactly one (customer, no rewrite
    needed since the verdict already hinted customer). Red: `state_out.focus.
    customers` comes back empty - `_reconcile_step`'s short circuit returns the INPUT
    state, before `_focus_rules` ever runs, so Cheng Huat Sentul's resolved entity is
    dropped along with the ambiguous "Sorento".
    """
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile())
    v = verdict(
        domain_hint=None,
        entities=[
            entity("Sorento", hint="customer"),
            entity("Cheng Huat Sentul", hint="customer", canonical_code=CHENG_HUAT_UUID),
        ],
    )
    resolved = {
        "Sorento": {"customer": 1, "transporter": 1},
        "Cheng Huat Sentul": {"customer": 1},
    }

    state_out, plan = apply(state, v, build_policy(), resolved=resolved)

    assert plan.ask is not None and plan.ask.kind == "kind_pick", (
        "the ambiguous word must still arm a kind pick"
    )
    assert state_out.focus.customers, (
        "Cheng Huat Sentul was resolved cleanly in the SAME message and must not be "
        "thrown away because a DIFFERENT token needed a pick"
    )
    names = [e.get("raw") for e in state_out.focus.customers]
    assert "Cheng Huat Sentul" in names, state_out.focus.customers


def test_two_ambiguous_tokens_are_asked_one_at_a_time():
    """AC-S8-2. Two ambiguous tokens in one message ("Sorento" and, say, "Mocha", both
    hitting two kinds each) - the pick slot holds one question at a time (owner
    ruling 6: "several ambiguous tokens are asked one pick at a time, first token
    first"). The SECOND ambiguous token must not be silently lost when the first is
    answered - it must still be asked once the first pick is answered.

    Red today: `reconcile.apply_reconciliation` only ever tracks ONE `kind_pick_
    options` list (the last ambiguous token wins, overwriting the first), and
    `_reconcile_step`'s short circuit drops any unresolved plan state anyway, so
    there is nowhere for a second pending pick to be queued at all.
    """
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile())
    v = verdict(
        domain_hint=None,
        entities=[
            entity("Sorento", hint="customer"),
            entity("Mocha", hint="customer"),
        ],
    )
    resolved = {
        "Sorento": {"customer": 1, "transporter": 1},
        "Mocha": {"customer": 1, "transporter": 1},
    }

    state1, plan1 = apply(state, v, build_policy(), resolved=resolved)

    assert plan1.ask is not None and plan1.ask.kind == "kind_pick"
    # Identified by LABEL, not `raw` (S7's own, separate fix - this test must not
    # depend on landing order between the two slices): each option's label is
    # "<token> (<kind>)" today even before S7 lands.
    first_labels = {o.get("label") for o in plan1.ask.options}
    assert all("Sorento" in (label or "") for label in first_labels), (
        f"the FIRST ambiguous token should be asked first, got options: {first_labels!r}"
    )

    # Answer the first pick (position 1 - "Sorento (transporter)").
    from app.services.chatbot.turn.state import State as _State

    state1 = _State(focus=state1.focus, pending=plan1.ask, profile=state1.profile)
    v2 = verdict(reference_positions=[1])
    state2, plan2 = apply(state1, v2, build_policy())

    # The second ambiguous token ("Mocha") must not have been lost - it is asked next.
    assert plan2.ask is not None and plan2.ask.kind == "kind_pick", (
        "the second ambiguous token must still be asked once the first pick is answered, "
        f"but no pick is open: plan.ask={plan2.ask!r}"
    )
    second_labels = {o.get("label") for o in plan2.ask.options}
    assert all("Mocha" in (label or "") for label in second_labels), second_labels


def test_t4_kind_pick_answer_sets_only_the_picked_kind():
    """AC-S8-2 (coordinator follow-up, 26 Sep, pinned via a full-engine replay before
    this test was written): a kind pick over a SINGLE ambiguous token
    ("Sorento" - customer or transporter) is a one-shot disambiguation, not a roster
    with several rows left to pick over time. Once position 2 ("customer") is
    answered:

    `state_out.focus.customers` is ALREADY correct today - it holds ONLY the picked
    customer entity (`raw: "Sorento"`), nothing lands in `focus.extra["transporter"]`
    at all. That is NOT the bug (asserted here as a guard, so a regression there is
    still caught).

    The real defect: `state_out.pending` is NOT cleared - `kind_pick` is one of
    `turn/pending.py::ROSTER_KINDS`, so `turn/apply.py::_answer_pending`'s roster arm
    (`if is_roster(pending.kind): return focus, with_answered_positions(pending,
    positions), None, True`) keeps the SAME kind_pick open forever, now carrying
    `answered_positions: [2]` - even though there is nothing left to disambiguate (a
    kind pick only ever has ONE useful answer). Measured on a full `engine.run_turn`
    replay (scratch, not committed): the session's `open_question` after T4 was still
    `{"kind": "kind_pick", "options": [...both...], "payload": {"answered_positions":
    [2]}}`, and it is THIS still-open pending's own unanswered option ("Sorento
    (transporter)") that a later lane reads as a second subject - the T4 reply printed
    "Transporter: Sorento" / "escalate to customer service team" alongside the correct
    "Customer: Sorento", even though `focus` itself never carried a transporter entity.
    Closing the kind pick once ANY position answers it removes the stale option a
    downstream reader could echo, and (a corollary AC-S11 would then cover cleanly)
    stops `escalate_offered` from being stamped onto a question that has nothing left
    to ask.
    """
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile(tier="office"))
    v1 = verdict(domain_hint=None, entities=[entity("Sorento", hint="customer")])
    resolved = {"Sorento": {"customer": 1, "transporter": 1}}

    state1, plan1 = apply(state, v1, build_policy(), resolved=resolved)
    assert plan1.ask is not None and plan1.ask.kind == "kind_pick"

    state1 = State(focus=state1.focus, pending=plan1.ask, profile=state1.profile)
    # Fix lane round 2, N1: the option order is the resolver's hit strength (ties
    # alphabetical), not the transcript's numbering, so the customer option's position
    # is read off the ask rather than assumed to be 2.
    customer_position = next(
        o["position"] for o in plan1.ask.options if o.get("entity_type") == "customer"
    )
    v2 = verdict(reference_positions=[customer_position])
    state2, _plan2 = apply(state1, v2, build_policy())

    # Guard (already true today): the picked kind lands cleanly, nothing else.
    names = [e.get("raw") for e in state2.focus.customers]
    assert names == ["Sorento"], state2.focus.customers
    assert not state2.focus.extra.get("transporter"), (
        f"no transporter entity may land on focus from answering the CUSTOMER pick: {state2.focus.extra!r}"
    )

    # Red: a single ambiguous token's kind pick, once answered, has nothing left to
    # ask - it must close, not stay open as a roster.
    assert state2.pending is None, (
        f"a one-shot kind pick must close once answered, not stay open carrying its "
        f"own unanswered sibling option: {state2.pending!r}"
    )
