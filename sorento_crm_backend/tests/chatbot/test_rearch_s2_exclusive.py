"""S2 - `scope_exclusive` replaces only the axes the message names (AC-1524,
PLAN-chatbot-turn-rearch.md, journey step 6: "SRT6536-DIY only").

RIGHT NOW every test is RED with `ModuleNotFoundError: No module named
'app.services.chatbot.turn'`.
"""
from __future__ import annotations

from tests.chatbot._turn_helpers import build_policy, entity, verdict


def _family_focus():
    """A customer family of 6 ledgers + one product, the journey-step-6 starting focus."""
    from app.services.chatbot.turn.state import Focus

    return Focus(
        customers=[{"raw": "chin chun", "hint": "customer", "family": True, "uuids": [f"c{i}" for i in range(6)]}],
        products=[entity("SRT6536-DIY")],
    )


def test_product_only_exclusive_narrows_product_and_keeps_customer_family():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Profile, State

    state = State(focus=_family_focus(), pending=None, profile=Profile())
    v = verdict(
        entities=[entity("SRT6536-DIY", hint="product")],
        scope_exclusive=True,
    )

    state2, _plan = apply(state, v, build_policy())

    assert [p["raw"] for p in state2.focus.products] == ["SRT6536-DIY"]
    assert state2.focus.customers == state.focus.customers


def test_location_only_exclusive_keeps_products_and_customer():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Profile, State

    state = State(focus=_family_focus(), pending=None, profile=Profile())
    v = verdict(
        entities=[entity("BRW", hint="warehouse")],
        scope_exclusive=True,
    )

    state2, _plan = apply(state, v, build_policy())

    assert state2.focus.products == state.focus.products
    assert state2.focus.customers == state.focus.customers


def test_customer_only_exclusive_keeps_products():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Profile, State

    state = State(focus=_family_focus(), pending=None, profile=Profile())
    v = verdict(
        entities=[entity("IBORN", hint="customer")],
        scope_exclusive=True,
    )

    state2, _plan = apply(state, v, build_policy())

    assert state2.focus.products == state.focus.products
