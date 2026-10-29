"""AGENTIC-P1 card section 3: the context a turn runs under, and the tools it may see.

Postgres via the blank schema (the new `chatbot_agent_enabled` column and the agent table
exist only once the ORM carries them). Refusal order is part of the contract:
contact_not_found, ai_replies_off, switch_off, no_linked_user.
"""
from __future__ import annotations

import pytest

from tests._pg_fixture import blank_session, unique_code
from tests.agent._seed import seed_contact, seed_user


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def _reason(db, respond_id):
    from app.services.agent.access import AgentRefused, build_context

    with pytest.raises(AgentRefused) as exc:
        build_context(db, respond_id)
    return exc.value.reason


def test_an_unknown_contact_is_contact_not_found(db):
    assert _reason(db, unique_code("nobody")) == "contact_not_found"


def test_ai_replies_off_is_refused_first_even_with_everything_else_missing(db):
    contact = seed_contact(db, chatbot_allowed=False, agent_enabled=False)
    assert _reason(db, contact["respond_id"]) == "ai_replies_off"


def test_switch_off_is_refused_before_the_linked_user_is_looked_at(db):
    contact = seed_contact(db, chatbot_allowed=True, agent_enabled=False)
    assert _reason(db, contact["respond_id"]) == "switch_off"


def test_no_linked_user_is_refused(db):
    contact = seed_contact(db)
    assert _reason(db, contact["respond_id"]) == "no_linked_user"


def test_an_inactive_linked_user_is_no_linked_user(db):
    contact = seed_contact(db)
    seed_user(db, contact_pk=contact["pk"], status="INACTIVE")
    assert _reason(db, contact["respond_id"]) == "no_linked_user"


def test_a_user_linked_to_another_contact_does_not_count(db):
    contact = seed_contact(db)
    other = seed_contact(db)
    seed_user(db, contact_pk=other["pk"])
    assert _reason(db, contact["respond_id"]) == "no_linked_user"


def test_success_fills_the_context(db):
    from app.services.agent.access import AgentContext, build_context

    contact = seed_contact(db)
    user_id = seed_user(db, contact_pk=contact["pk"])

    ctx = build_context(db, contact["respond_id"])

    assert isinstance(ctx, AgentContext)
    assert ctx.contact_pk == contact["pk"]
    assert ctx.contact_respond_id == contact["respond_id"]
    assert ctx.user_id == user_id
    assert ctx.user_name == "ZZT Agent User"
    assert isinstance(ctx.grants, frozenset)


def test_the_context_is_immutable(db):
    from app.services.agent.access import build_context

    contact = seed_contact(db)
    seed_user(db, contact_pk=contact["pk"])
    ctx = build_context(db, contact["respond_id"])
    with pytest.raises(Exception):
        ctx.user_id = "someone-else"  # frozen dataclass


def test_permitted_tools_returns_only_tools_whose_slug_the_user_holds(db):
    from app.services.agent.access import build_context, permitted_tools

    contact = seed_contact(db)
    seed_user(db, contact_pk=contact["pk"], slugs=["inventory.stock.view"])
    ctx = build_context(db, contact["respond_id"])

    tools = permitted_tools(db, ctx)

    assert [t.name for t in tools] == ["crm_inventory_stock_balance_list"]


def test_a_user_with_no_role_gets_no_tools(db):
    from app.services.agent.access import build_context, permitted_tools

    contact = seed_contact(db)
    seed_user(db, contact_pk=contact["pk"], slugs=[])
    ctx = build_context(db, contact["respond_id"])

    assert permitted_tools(db, ctx) == []


def test_two_slugs_expose_every_tool_behind_them(db):
    from app.services.agent.access import build_context, permitted_tools

    contact = seed_contact(db)
    seed_user(
        db,
        contact_pk=contact["pk"],
        slugs=["order_management.orders.view", "procurement.packing_lists.view"],
    )
    ctx = build_context(db, contact["respond_id"])

    assert {t.name for t in permitted_tools(db, ctx)} == {
        "crm_report_ask",
        "crm_order_management_orders_by_product_list",
        "crm_incoming_stock_by_product",
        "crm_incoming_stock_shipments",
    }
