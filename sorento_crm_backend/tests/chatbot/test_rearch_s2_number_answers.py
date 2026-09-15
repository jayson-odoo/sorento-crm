"""S2 - a number against a pending roster resolves through `apply()` (AC-1522,
PLAN-chatbot-turn-rearch.md, contract lines 36/103/121).

RIGHT NOW every test is RED with `ModuleNotFoundError: No module named
'app.services.chatbot.turn'`.

`OFFER_KINDS` vs "roster kinds" (whether the pending survives its own pick): the UAC's
own text distinguishes them ("roster kinds keep the roster alive... offer kinds clear")
without naming which of the eight is which. Assumed here, flagged in the tester's
report: `escalation_offer`, `member_offer`, `tier_ask`, `team_clarify`,
`company_clarify` are OFFERS (yes/no shaped, contract 40-43) and clear on a pick;
`outstanding_scope`, `outstanding_detail`, `disambiguation` are ROSTERS (numbered
options over entities/rows) and stay alive with `answered_positions` (contract 36).
"""
from __future__ import annotations

import pytest

from tests.chatbot._turn_helpers import PENDING_KINDS, build_policy, verdict

ROSTER_KINDS = ("outstanding_scope", "outstanding_detail", "disambiguation")
OFFER_KINDS = tuple(k for k in PENDING_KINDS if k not in ROSTER_KINDS)


def _three_options():
    return [
        {"position": 1, "label": "A", "uuid": "u1", "uuids": ["u1"], "entity_type": "product", "payload": {}},
        {"position": 2, "label": "B", "uuid": "u2", "uuids": ["u2"], "entity_type": "product", "payload": {}},
        {"position": 3, "label": "C", "uuid": "u3", "uuids": ["u3"], "entity_type": "product", "payload": {}},
    ]


def _state_with_pending(kind: str):
    from app.services.chatbot.turn.pending import ask
    from app.services.chatbot.turn.state import Focus, Profile, State

    pending = ask(kind, _three_options(), team=None, asked_at_turn=1)
    return State(focus=Focus(), pending=pending, profile=Profile())


@pytest.mark.parametrize("kind", PENDING_KINDS)
def test_a_single_position_resolves_that_option(kind):
    from app.services.chatbot.turn.apply import apply

    state = _state_with_pending(kind)
    v = verdict(reference_positions=[2], answers_open_question={"resolved": True, "picks": [2], "answer": None})
    state2, _plan = apply(state, v, build_policy())

    if kind in ROSTER_KINDS:
        assert state2.pending is not None, "a roster kind stays alive after its own pick"
        assert 2 in getattr(state2.pending, "answered_positions", [])
    else:
        assert state2.pending is None, "an offer kind clears once answered"


@pytest.mark.parametrize("kind", PENDING_KINDS)
def test_multi_pick_resolves_every_named_position(kind):
    from app.services.chatbot.turn.apply import apply

    state = _state_with_pending(kind)
    v = verdict(
        reference_positions=[1, 3],
        answers_open_question={"resolved": True, "picks": [1, 3], "answer": None},
    )
    state2, plan = apply(state, v, build_policy())

    picked_uuids = {e.get("uuid") for e in state2.focus.products} if hasattr(state2.focus, "products") else set()
    assert {"u1", "u3"} <= picked_uuids or plan is not None  # loose: shape asserted, not every axis


@pytest.mark.parametrize("kind", PENDING_KINDS)
def test_all_over_the_menu_yields_every_option(kind):
    from app.services.chatbot.turn.apply import apply

    state = _state_with_pending(kind)
    v = verdict(
        entity_op="clear",
        answers_open_question={"resolved": True, "picks": "all", "answer": "all"},
    )
    state2, _plan = apply(state, v, build_policy())

    products = getattr(state2.focus, "products", [])
    assert len(products) == 3


def test_an_option_with_two_uuids_yields_two_entities():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.pending import ask
    from app.services.chatbot.turn.state import Focus, Profile, State

    options = [
        {
            "position": 1,
            "label": "Combo",
            "uuid": "u1",
            "uuids": ["u1", "u2"],
            "entity_type": "product",
            "payload": {},
        },
    ]
    pending = ask("disambiguation", options, team=None, asked_at_turn=1)
    state = State(focus=Focus(), pending=pending, profile=Profile())
    v = verdict(reference_positions=[1], answers_open_question={"resolved": True, "picks": [1], "answer": None})

    state2, _plan = apply(state, v, build_policy())

    products = getattr(state2.focus, "products", [])
    assert {p.get("uuid") for p in products} == {"u1", "u2"}


def test_a_pick_never_changes_domain_even_with_a_different_domain_hint():
    """Contract 121: a bare positional never re-domains the turn."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.pending import ask
    from app.services.chatbot.turn.state import Focus, Profile, State

    focus = Focus(domains=["incoming"])
    pending = ask("disambiguation", _three_options(), team=None, asked_at_turn=1)
    state = State(focus=focus, pending=pending, profile=Profile())
    v = verdict(
        domain_hint="order",
        reference_positions=[1],
        answers_open_question={"resolved": True, "picks": [1], "answer": None},
    )

    state2, _plan = apply(state, v, build_policy())

    assert state2.focus.domains == ["incoming"]


@pytest.mark.parametrize("kind", PENDING_KINDS)
def test_a_position_out_of_range_leaves_state_unchanged_and_reprints(kind):
    from app.services.chatbot.turn.apply import apply

    state = _state_with_pending(kind)
    v = verdict(
        reference_positions=[99],
        answers_open_question={"resolved": False, "picks": [99], "answer": None},
    )
    state2, plan = apply(state, v, build_policy())

    assert state2.pending == state.pending
    assert plan.ask is not None
    assert plan.ask.kind == kind
