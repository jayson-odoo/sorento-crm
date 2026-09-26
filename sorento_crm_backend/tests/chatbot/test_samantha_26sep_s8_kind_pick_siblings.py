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
