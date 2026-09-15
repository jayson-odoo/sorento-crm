"""S2 - the narrower reads the domain row's `narrowing` map and returns proceed / ask
roster / ask type / ask tier / filter optional, per (domain, entity kind) (AC-1526,
PLAN-chatbot-turn-rearch.md), parametrized over the six triples AC-1526/AC-1501 name.

RIGHT NOW every test is RED with `ModuleNotFoundError: No module named
'app.services.chatbot.turn'`.
"""
from __future__ import annotations

from tests.chatbot._turn_helpers import build_policy, entity, verdict


def _family(prefix: str, count: int):
    return [entity(f"{prefix}{i}", hint="product") for i in range(count)]


def test_inventory_product_family_lists_all_ten_no_ask():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile())
    v = verdict(domain_hint="inventory", entities=_family("SRTFAM", 10))

    _state2, plan = apply(state, v, build_policy())

    assert plan.ask is None
    fetch_domains = [f.domain for f in plan.fetch] if plan.fetch else []
    assert "inventory" in fetch_domains
    inventory_fetch = next(f for f in plan.fetch if f.domain == "inventory")
    assert len(inventory_fetch.entities) == 10


def test_incoming_product_family_asks_product_pick_with_ten_options_not_list_all():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile())
    v = verdict(domain_hint="incoming", entities=_family("SRTFAM", 10))

    _state2, plan = apply(state, v, build_policy())

    assert plan.ask is not None
    assert plan.ask.kind == "product_pick"
    assert len(plan.ask.options) == 10
    assert getattr(plan.ask, "list_all", False) is False


def test_purchase_cost_product_family_asks_product_pick():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile())
    v = verdict(domain_hint="purchase_cost", entities=_family("SRTFAM", 10))

    _state2, plan = apply(state, v, build_policy())

    assert plan.ask is not None
    assert plan.ask.kind == "product_pick"


def test_order_customer_with_three_candidate_families_asks_customer_pick():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile())
    v = verdict(
        domain_hint="order",
        entities=[entity("chin", hint="customer"), entity("chun", hint="customer"), entity("chan", hint="customer")],
    )

    _state2, plan = apply(state, v, build_policy())

    assert plan.ask is not None
    assert plan.ask.kind == "customer_pick"


def test_product_attachment_with_no_attachment_type_asks_type():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile())
    v = verdict(domain_hint="product_attachment", entities=[entity("SRTWC8517", hint="product")])

    _state2, plan = apply(state, v, build_policy())

    assert plan.ask is not None
    assert plan.ask.kind == "attachment_type_ask"


def test_promotion_with_no_tier_and_no_profile_tier_asks_tier():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile(tier=None))
    v = verdict(domain_hint="promotion", entities=[])

    _state2, plan = apply(state, v, build_policy())

    assert plan.ask is not None
    assert plan.ask.kind == "tier_pick"


def test_promotion_with_profile_tier_dealer_fetches_filtered_no_ask():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile(tier="dealer"))
    v = verdict(domain_hint="promotion", entities=[])

    _state2, plan = apply(state, v, build_policy())

    assert plan.ask is None
    promotion_fetch = next(f for f in plan.fetch if f.domain == "promotion")
    assert promotion_fetch.filters.get("tier") == "dealer"
