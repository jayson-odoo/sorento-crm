"""Fix, 7 Sep 2026: `include_specs` / `include_sellable` / `include_pipeline` are opt-in
from the CALLER, not a server-level default.

Owner report: `sorento_crm_mcp/server.py`'s `TOOL_DEFAULT_QUERY_PARAMS` used to default
`include_sellable` / `include_specs` ON for every caller of the shared MCP server - n8n's
production business logic included, not the CRM chatbot alone - so a live deploy would
have shown dealers sellable stock and a wall of specs with no field-reveal filter (n8n's
own renderer prints fields as given). `entity_ids_transformer` is where the CRM's OWN turn
now opts in, per turn, for the reason that turn actually has.

`documentation/plans/chatbot/PLAN-chatbot-growth-r1.md` Slice A (A1 spec projection, A2
sellable, A3 the three-line pipeline).
"""
from __future__ import annotations

from app.services.chatbot.lanes.business import fetch


# --------------------------------------------------------------------------- #
# A1: include_specs, gated on a product-check intent or the master_products domain.
# --------------------------------------------------------------------------- #


def test_include_specs_set_on_check_product_intent():
    trigger = {
        "entities": [],
        "tool": "crm_master_products_list",
        "semantic_input": {"intent_hint": "check_product", "contact_id": "1", "space_id": "s"},
    }
    out = fetch.entity_ids_transformer(trigger)
    assert out["include_specs"] is True


def test_include_specs_set_on_master_products_domain():
    trigger = {
        "entities": [],
        "tool": "crm_master_products_list",
        "semantic_input": {"domain_hint": "master_products", "contact_id": "1", "space_id": "s"},
    }
    out = fetch.entity_ids_transformer(trigger)
    assert out["include_specs"] is True


def test_include_specs_absent_when_neither_intent_nor_domain_matches():
    """The OLD parameter set: a products call this plan did not touch stays unchanged."""
    trigger = {
        "entities": [],
        "tool": "crm_master_products_list",
        "semantic_input": {"intent_hint": "check_price", "domain_hint": None, "contact_id": "1", "space_id": "s"},
    }
    out = fetch.entity_ids_transformer(trigger)
    assert "include_specs" not in out


def test_include_specs_never_set_for_a_different_tool():
    trigger = {
        "entities": [],
        "tool": "crm_inventory_stock_balance_list",
        "semantic_input": {"intent_hint": "check_product", "domain_hint": "master_products", "contact_id": "1", "space_id": "s"},
    }
    out = fetch.entity_ids_transformer(trigger)
    assert "include_specs" not in out


# --------------------------------------------------------------------------- #
# A2: include_sellable, gated on the CONTACT's own inventory.sellable grant.
# --------------------------------------------------------------------------- #


def test_include_sellable_set_when_the_contact_holds_the_grant():
    trigger = {
        "entities": [],
        "tool": "crm_inventory_stock_balance_list",
        "semantic_input": {"contact_id": "1", "space_id": "s"},
        "access": {"attributes": ["inventory.sellable"]},
    }
    out = fetch.entity_ids_transformer(trigger)
    assert out["include_sellable"] is True


def test_include_sellable_absent_with_no_access_block():
    """The OLD parameter set: a stock call with no `access` (every call before Slice C's
    field-reveal wiring landed, and every non-CRM caller) stays unchanged."""
    trigger = {
        "entities": [],
        "tool": "crm_inventory_stock_balance_list",
        "semantic_input": {"contact_id": "1", "space_id": "s"},
    }
    out = fetch.entity_ids_transformer(trigger)
    assert "include_sellable" not in out


def test_include_sellable_absent_without_the_specific_grant():
    trigger = {
        "entities": [],
        "tool": "crm_inventory_stock_balance_list",
        "semantic_input": {"contact_id": "1", "space_id": "s"},
        "access": {"attributes": ["purchase_orders.supplier"]},
    }
    out = fetch.entity_ids_transformer(trigger)
    assert "include_sellable" not in out


def test_include_sellable_never_set_for_a_different_tool():
    trigger = {
        "entities": [],
        "tool": "crm_master_products_list",
        "semantic_input": {"contact_id": "1", "space_id": "s"},
        "access": {"attributes": ["inventory.sellable"]},
    }
    out = fetch.entity_ids_transformer(trigger)
    assert "include_sellable" not in out


# --------------------------------------------------------------------------- #
# A3: include_pipeline rides ALONGSIDE include_summary on a quantity ask, and only then.
# --------------------------------------------------------------------------- #


def test_include_pipeline_set_alongside_include_summary_on_a_quantity_ask():
    trigger = {
        "entities": [],
        "tool": "crm_order_management_orders_list",
        "semantic_input": {
            "requested_attributes": ["quantity"], "contact_id": "1", "space_id": "s",
        },
    }
    out = fetch.entity_ids_transformer(trigger)
    assert out["include_summary"] is True
    assert out["include_pipeline"] is True


def test_include_pipeline_absent_on_a_plain_do_list():
    """The OLD parameter set: n8n's own quantity-ask workflow sends `include_summary`
    but has never heard of `include_pipeline` - a plain list must carry neither."""
    trigger = {
        "entities": [],
        "tool": "crm_order_management_orders_list",
        "semantic_input": {"contact_id": "1", "space_id": "s"},
    }
    out = fetch.entity_ids_transformer(trigger)
    assert "include_summary" not in out
    assert "include_pipeline" not in out


def test_every_order_tool_declares_include_pipeline_on_its_toolspec():
    """Review round 2, nit 1: `fetch.py` sets `include_pipeline` for every `ORDER_TOOLS`
    member; the MCP strips a param the ToolSpec does not declare, so each member must
    declare it (both do - orders_list and orders_by_product_list)."""
    from app.services.chatbot.lanes.business.fetch import ORDER_TOOLS
    from app.services.mcp_tool_capability_service import _load_catalog_specs

    specs = {spec.name: spec for spec in _load_catalog_specs()}
    for name in ORDER_TOOLS:
        assert "include_pipeline" in tuple(specs[name].query_params), name
