"""S2 - reconciliation: the resolver is asked for the hinted kind first; a miss with
exactly one other kind hitting rewrites the kind; two kinds hitting asks (AC-1527,
PLAN-chatbot-turn-rearch.md). `ResolvedKinds` is constructed by hand per the captain's
brief - tests do not call a real resolver (that seam is S3).

The roster-equality half of AC-1527 ("a customer roster is identical with or without a
product token in the message") needs the S3 resolver seam and is explicitly out of
scope here per the captain's brief.

RIGHT NOW every test is RED with `ModuleNotFoundError: No module named
'app.services.chatbot.turn'`.
"""
from __future__ import annotations

from tests.chatbot._turn_helpers import build_policy, entity, verdict


def test_a_miss_with_one_other_hit_rewrites_the_kind_and_traces_it():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile())
    v = verdict(
        domain_hint=None,
        entities=[entity("7445", hint="order")],
    )
    resolved = {"7445": {"order": 0, "product": 1}}

    state2, plan = apply(state, v, build_policy(), resolved=resolved)

    assert any(p.get("raw") == "7445" for p in state2.focus.products)
    assert plan.trace.reconciled == [("7445", "order", "product")]


def test_domain_follows_the_reconciled_kind_when_the_verdict_named_no_domain():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile())
    v = verdict(domain_hint=None, entities=[entity("7445", hint="order")])
    resolved = {"7445": {"order": 0, "product": 1}}

    state2, _plan = apply(state, v, build_policy(), resolved=resolved)

    assert state2.focus.domains == ["inventory"]


def test_domain_is_unchanged_when_the_verdict_named_its_own_domain_word():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(domains=["order"]), pending=None, profile=Profile())
    v = verdict(domain_hint="order", entities=[entity("7445", hint="order")])
    resolved = {"7445": {"order": 0, "product": 1}}

    state2, _plan = apply(state, v, build_policy(), resolved=resolved)

    assert state2.focus.domains == ["order"]


def test_two_kinds_hitting_produces_a_kind_pick_ask():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile())
    v = verdict(domain_hint=None, entities=[entity("7445", hint="order")])
    resolved = {"7445": {"order": 1, "product": 1}}

    _state2, plan = apply(state, v, build_policy(), resolved=resolved)

    assert plan.ask is not None
    assert plan.ask.kind == "kind_pick"
    assert len(plan.ask.options) == 2


def test_resolved_none_does_no_reconciliation():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile())
    v = verdict(domain_hint=None, entities=[entity("7445", hint="order")])

    _state2, plan = apply(state, v, build_policy(), resolved=None)

    assert plan.trace.reconciled == []
