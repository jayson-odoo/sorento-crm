"""S2 - `Plan` is data; `route()` reads the plan and nothing else (AC-1528,
PLAN-chatbot-turn-rearch.md).

RIGHT NOW every test is RED with `ModuleNotFoundError: No module named
'app.services.chatbot.turn'`.
"""
from __future__ import annotations

import inspect

from tests.chatbot._turn_helpers import build_policy, entity, verdict


def test_plan_has_the_contract_fields():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile())
    v = verdict(domain_hint="inventory", entities=[entity("SRTWC8517")])

    _state2, plan = apply(state, v, build_policy())

    fields = set(getattr(type(plan), "__dataclass_fields__", {})) or set(
        getattr(type(plan), "model_fields", {})
    )
    assert fields == {"domains", "fetch", "ask", "denied", "trace"}


def test_fetch_spec_has_the_contract_fields():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile())
    v = verdict(domain_hint="inventory", entities=[entity("SRTWC8517")])

    _state2, plan = apply(state, v, build_policy())

    assert plan.fetch, "expected at least one FetchSpec for a resolved domain"
    spec = plan.fetch[0]
    fields = set(getattr(type(spec), "__dataclass_fields__", {})) or set(
        getattr(type(spec), "model_fields", {})
    )
    assert fields == {"domain", "entities", "filters", "date_window"}


def test_trace_has_the_contract_fields():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile())
    v = verdict(domain_hint="inventory", entities=[entity("SRTWC8517")])

    _state2, plan = apply(state, v, build_policy())

    fields = set(getattr(type(plan.trace), "__dataclass_fields__", {})) or set(
        getattr(type(plan.trace), "model_fields", {})
    )
    assert {"rules_fired", "state_diff", "narrowing", "reconciled"} <= fields


def test_domains_are_in_message_order_for_a_two_domain_verdict():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile())
    v = verdict(
        entities=[entity("SRTWT2634", hint="product")],
        # Two-domain messages (captain ruling, item 3, 16 Sep 2026): message-order
        # list of {domain, intent}; `focus.domains` = [a["domain"] for a in asks].
        asks=[
            {"domain": "inventory", "intent": "check_stock"},
            {"domain": "incoming", "intent": "check_incoming"},
        ],
    )

    state2, plan = apply(state, v, build_policy())

    assert plan.domains == ["inventory", "incoming"]
    assert state2.focus.domains == ["inventory", "incoming"]


def test_domains_falls_back_to_domain_hint_when_asks_is_empty():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile())
    v = verdict(domain_hint="inventory", entities=[entity("SRTWT2634")], asks=[])

    state2, plan = apply(state, v, build_policy())

    assert plan.domains == ["inventory"]
    assert state2.focus.domains == ["inventory"]


def test_denied_lists_a_domain_the_profile_grants_forbid():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile(grants=[]))
    v = verdict(domain_hint="purchase_cost", entities=[entity("SRTWC8517")])

    _state2, plan = apply(state, v, build_policy())

    assert "purchase_cost" in plan.denied


def test_route_takes_only_a_plan():
    from app.services.chatbot.turn.route import route

    sig = inspect.signature(route)
    params = list(sig.parameters)
    assert params == ["plan"], params


def test_route_returns_one_of_the_thirteen_branch_kinds():
    from app.services.chatbot.contracts import BRANCH_KINDS
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.route import route
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile())
    v = verdict(domain_hint="inventory", entities=[entity("SRTWC8517")])

    _state2, plan = apply(state, v, build_policy())
    branch_kind = route(plan)

    assert branch_kind in BRANCH_KINDS
