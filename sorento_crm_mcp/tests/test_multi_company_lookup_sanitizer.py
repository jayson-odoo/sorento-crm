"""AC-C5 (UAC multi-company-reply-clarity): `_sanitize_tool_response` must not
drop `company_name` (row-level) or `lookup_companies` (top-level) on their way
to the presenter, for every slimmer that touches an affected tool's payload.

Every slimmer these tools run through (`_slim_orders_list_row`,
`_strip_products_list_confidential`, `_strip_promotions_list_row_ids`,
`_slim_promotion_products_response`, `_slim_stock_nested_warehouse`) is a
DENY-list (drops named keys, keeps everything else) rather than an allow-list
projection, so these assertions are expected to PASS today without any code
change - this is a regression guard against a future slimmer becoming an
allow-list and silently swallowing the new fields, not a red TDD test like
the presenter suite in test_presenters.py.
"""
from __future__ import annotations

import json

from sorento_crm_mcp.server import _sanitize_tool_response


def _company_block():
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "name": "Sorento",
    }


def test_orders_list_sanitizer_keeps_company_fields():
    raw = json.dumps({
        "data": [{
            "id": "11111111-1111-1111-1111-111111111111",
            "order_number": "DO-1", "company_id": "cid-1", "company_name": "Mocha",
            "lines": [],
        }],
        "lookup_companies": [_company_block()],
    })

    sanitized = json.loads(_sanitize_tool_response("crm_order_management_orders_list", raw))

    assert sanitized["data"][0]["company_name"] == "Mocha"
    assert sanitized["lookup_companies"] == [_company_block()]


def test_products_list_sanitizer_keeps_company_fields():
    raw = json.dumps({
        "data": [{
            "id": "product-1", "product_code": "A", "company_id": "cid-1",
            "company_name": "Mocha", "cost_price": 5,
        }],
        "lookup_companies": [_company_block()],
    })

    sanitized = json.loads(_sanitize_tool_response("crm_master_products_list", raw))

    assert sanitized["data"][0]["company_name"] == "Mocha"
    # The confidential-strip is still doing its own job alongside the new fields.
    assert "cost_price" not in sanitized["data"][0]
    assert sanitized["lookup_companies"] == [_company_block()]


def test_promotions_list_sanitizer_keeps_company_fields():
    raw = json.dumps({
        "data": [{
            "id": "promo-1", "description": "Promo A", "company_id": "cid-1",
            "company_name": "Mocha",
        }],
        "lookup_companies": [_company_block()],
    })

    sanitized = json.loads(_sanitize_tool_response("crm_marketing_promotions_list", raw))

    assert sanitized["data"][0]["company_name"] == "Mocha"
    assert sanitized["lookup_companies"] == [_company_block()]


def test_promotion_products_list_sanitizer_keeps_company_fields():
    raw = json.dumps({
        "data": [{
            "id": "pp-1", "product": {"product_code": "A"}, "promotion": {"description": "Promo A"},
            "company_id": "cid-1", "company_name": "Mocha",
        }],
        "lookup_companies": [_company_block()],
    })

    sanitized = json.loads(
        _sanitize_tool_response("crm_marketing_promotion_products_list", raw)
    )

    assert sanitized["data"][0]["company_name"] == "Mocha"
    assert sanitized["lookup_companies"] == [_company_block()]


def test_incoming_stock_list_sanitizer_keeps_company_fields():
    """Incoming-stock tools run no row-slimmer at all today - the raw payload
    (minus updated_at normalization) reaches the presenter unchanged."""
    raw = json.dumps({
        "data": [{"shipment_number": "SH1", "company_id": "cid-1", "company_name": "Mocha", "lines": []}],
        "lookup_companies": [_company_block()],
    })

    sanitized = json.loads(_sanitize_tool_response("crm_incoming_stock_list", raw))

    assert sanitized["data"][0]["company_name"] == "Mocha"
    assert sanitized["lookup_companies"] == [_company_block()]


def test_stock_balance_sanitizer_keeps_company_fields():
    raw = json.dumps({
        "data": [{
            "id": "stock-1", "quantity_on_hand": 5, "quantity_available": 5,
            "quantity_reserved": 0, "quantity_damaged": 0, "status": "normal",
            "company_id": "cid-1", "company_name": "Mocha",
            "product": {"product_code": "A"}, "warehouse": {"warehouse_code": "BRW"},
        }],
        "lookup_companies": [_company_block()],
    })

    sanitized = json.loads(_sanitize_tool_response("crm_inventory_stock_balance_list", raw))

    assert sanitized["data"][0]["company_name"] == "Mocha"
    assert sanitized["lookup_companies"] == [_company_block()]


# --- F2 (review round): the raw row company_id UUID never reaches the agent ---
#
# `company_id` arrives on every row now that the affected schemas declare it and
# the rows are ORM instances (`from_attributes` fills it in). It is a UUID, and
# the whole point of the row slimmers is that no UUID reaches an agent-facing
# row, so the sanitizer drops it for every tool. `company_name` is the readable
# form the presenter shows; top-level `lookup_companies` keeps its ids because
# n8n matches on them.


def test_stock_balance_sanitizer_drops_row_company_id():
    raw = json.dumps({
        "data": [{
            "id": "stock-1", "quantity_on_hand": 5, "quantity_available": 5,
            "quantity_reserved": 0, "quantity_damaged": 0, "status": "normal",
            "company_id": "00000000-0000-0000-0000-000000000002",
            "company_name": "Mocha",
            "product": {"product_code": "A"}, "warehouse": {"warehouse_code": "BRW"},
        }],
        "lookup_companies": [_company_block()],
    })

    sanitized = json.loads(_sanitize_tool_response("crm_inventory_stock_balance_list", raw))

    assert "company_id" not in sanitized["data"][0]
    assert sanitized["data"][0]["company_name"] == "Mocha"
    assert sanitized["lookup_companies"] == [_company_block()]


def test_orders_list_sanitizer_drops_row_company_id():
    raw = json.dumps({
        "data": [{
            "id": "11111111-1111-1111-1111-111111111111",
            "order_number": "DO-1",
            "company_id": "00000000-0000-0000-0000-000000000002",
            "company_name": "Mocha",
            "lines": [],
        }],
        "lookup_companies": [_company_block()],
    })

    sanitized = json.loads(_sanitize_tool_response("crm_order_management_orders_list", raw))

    assert "company_id" not in sanitized["data"][0]
    assert sanitized["data"][0]["company_name"] == "Mocha"
    assert sanitized["lookup_companies"] == [_company_block()]


def test_products_list_sanitizer_drops_row_company_id():
    raw = json.dumps({
        "data": [{
            "id": "product-1", "product_code": "A",
            "company_id": "00000000-0000-0000-0000-000000000002",
            "company_name": "Mocha", "cost_price": 5,
        }],
        "lookup_companies": [_company_block()],
    })

    sanitized = json.loads(_sanitize_tool_response("crm_master_products_list", raw))

    assert "company_id" not in sanitized["data"][0]
    assert sanitized["data"][0]["company_name"] == "Mocha"
    assert sanitized["lookup_companies"] == [_company_block()]


def test_promotions_list_sanitizer_drops_row_company_id():
    raw = json.dumps({
        "data": [{
            "id": "promo-1", "description": "Promo A",
            "company_id": "00000000-0000-0000-0000-000000000002",
            "company_name": "Mocha",
        }],
        "lookup_companies": [_company_block()],
    })

    sanitized = json.loads(_sanitize_tool_response("crm_marketing_promotions_list", raw))

    assert "company_id" not in sanitized["data"][0]
    assert sanitized["data"][0]["company_name"] == "Mocha"
    assert sanitized["lookup_companies"] == [_company_block()]


def test_promotion_products_sanitizer_drops_nested_company_id():
    """The promotion-products row nests `product` and `promotion` objects, each
    an ORM row of its own, so the UUID can arrive one level down too."""
    raw = json.dumps({
        "data": [{
            "id": "pp-1",
            "company_id": "00000000-0000-0000-0000-000000000002",
            "company_name": "Mocha",
            "product": {
                "product_code": "A",
                "company_id": "00000000-0000-0000-0000-000000000002",
            },
            "promotion": {"description": "Promo A"},
        }],
        "lookup_companies": [_company_block()],
    })

    sanitized = json.loads(
        _sanitize_tool_response("crm_marketing_promotion_products_list", raw)
    )

    row = sanitized["data"][0]
    assert "company_id" not in row
    assert "company_id" not in row["product"]
    assert row["company_name"] == "Mocha"
    assert sanitized["lookup_companies"] == [_company_block()]


def test_incoming_stock_list_sanitizer_drops_row_company_id():
    raw = json.dumps({
        "data": [{
            "shipment_number": "SH1",
            "company_id": "00000000-0000-0000-0000-000000000002",
            "company_name": "Mocha", "lines": [],
        }],
        "lookup_companies": [_company_block()],
    })

    sanitized = json.loads(_sanitize_tool_response("crm_incoming_stock_list", raw))

    assert "company_id" not in sanitized["data"][0]
    assert sanitized["data"][0]["company_name"] == "Mocha"
    assert sanitized["lookup_companies"] == [_company_block()]
