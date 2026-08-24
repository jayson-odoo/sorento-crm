"""Tests for the warehouse-master key relabel layer applied to
`crm_inventory_*` MCP tool responses. Backend payloads still emit
`warehouse_code` / `warehouse_name` / `location` (n8n + Sage push compat);
MCP rewrites the keys to the Sage-aligned vocabulary before returning to
the caller.
"""
import json

from sorento_crm_mcp.server import _sanitize_tool_response


def test_inventory_tool_top_level_warehouse_keys_are_relabeled():
    raw = json.dumps(
        {
            "data": [
                {
                    "id": "wh-1",
                    "warehouse_code": "WH-001",
                    "warehouse_name": "Selangor Main DC",
                    "location": "Shah Alam",
                    "is_active": True,
                }
            ],
            "pagination": {"total": 1, "page": 1, "limit": 50},
        }
    )

    sanitized = json.loads(
        _sanitize_tool_response("crm_inventory_warehouses_list", raw)
    )
    row = sanitized["data"][0]

    assert row["system_location"] == "WH-001"
    assert row["system_location_description"] == "Selangor Main DC"
    assert row["warehouse"] == "Shah Alam"
    assert "warehouse_code" not in row
    assert "warehouse_name" not in row
    assert "location" not in row


def test_inventory_warehouse_list_keeps_full_relabeled_record():
    """`crm_inventory_warehouses_list` is the master record - keep all fields,
    just relabeled. Slimming only applies to nested `warehouse` on stock rows."""
    raw = json.dumps(
        {
            "data": [
                {
                    "id": "wh-1",
                    "warehouse_code": "WH-001",
                    "warehouse_name": "Selangor Main DC",
                    "location": "Shah Alam",
                }
            ]
        }
    )

    sanitized = json.loads(
        _sanitize_tool_response("crm_inventory_warehouses_list", raw)
    )
    row = sanitized["data"][0]

    assert row["id"] == "wh-1"
    assert row["system_location"] == "WH-001"
    assert row["system_location_description"] == "Selangor Main DC"
    assert row["warehouse"] == "Shah Alam"


def test_stock_row_top_level_renames_warehouse_id_and_strips_zone_id():
    raw = json.dumps(
        {
            "data": [
                {
                    "id": "stock-1",
                    "product_id": "prod-uuid",
                    "warehouse_id": "wh-uuid",
                    "zone_id": None,
                    "quantity_on_hand": 197,
                }
            ]
        }
    )

    sanitized = json.loads(
        _sanitize_tool_response("crm_inventory_stock_balance_list", raw)
    )
    row = sanitized["data"][0]

    assert row["system_location_id"] == "wh-uuid"
    assert "warehouse_id" not in row
    assert "zone_id" not in row
    assert row["product_id"] == "prod-uuid"
    assert row["quantity_on_hand"] == 197


def test_stock_row_nested_warehouse_is_renamed_and_slimmed_to_literal_text_only():
    """The nested warehouse wrapper on a stock row is renamed to
    `system_location` and trimmed to literal text only
    (system_location + warehouse). No UUID, no description."""
    raw = json.dumps(
        {
            "data": [
                {
                    "id": "stock-1",
                    "quantity_on_hand": 12,
                    "warehouse": {
                        "id": "wh-1",
                        "warehouse_code": "BRW",
                        "warehouse_name": "Bukit Raja Warehouse",
                        "location": "BRW",
                    },
                }
            ]
        }
    )

    sanitized = json.loads(
        _sanitize_tool_response("crm_inventory_stock_balance_list", raw)
    )
    row = sanitized["data"][0]
    assert "warehouse" not in row
    nested = row["system_location"]

    assert nested == {"system_location": "BRW", "warehouse": "BRW"}
    assert "id" not in nested
    assert "system_location_description" not in nested


def test_inventory_stock_tool_still_strips_hidden_fields_after_relabel():
    """`crm_inventory_stock_*` should hit both passes: strip + relabel."""
    raw = json.dumps(
        {
            "data": [
                {
                    "id": "stock-1",
                    "quantity_on_hand": 5,
                    "quantity_available": 4,
                    "quantity_reserved": 1,
                    "warehouse_code": "WH-001",
                    "warehouse_name": "Selangor Main DC",
                }
            ]
        }
    )

    sanitized = json.loads(
        _sanitize_tool_response("crm_inventory_stock_balance_list", raw)
    )
    row = sanitized["data"][0]

    assert row["quantity_on_hand"] == 5
    assert "quantity_available" not in row
    assert "quantity_reserved" not in row
    assert row["system_location"] == "WH-001"
    assert row["system_location_description"] == "Selangor Main DC"


def test_non_inventory_tool_keeps_legacy_warehouse_keys():
    """Order-management / incoming-stock tools still expose warehouse_code etc."""
    raw = json.dumps(
        {
            "data": [
                {
                    "id": "order-1",
                    "warehouse_code": "WH-001",
                    "warehouse_name": "Selangor Main DC",
                }
            ]
        }
    )

    sanitized = json.loads(
        _sanitize_tool_response("crm_order_management_orders_list", raw)
    )
    row = sanitized["data"][0]

    assert row["warehouse_code"] == "WH-001"
    assert row["warehouse_name"] == "Selangor Main DC"
    assert "system_location" not in row
    assert "system_location_description" not in row


def test_collision_guard_preserves_existing_target_key():
    """If a dict already carries a target key (e.g. a nested `warehouse`
    object alongside a scalar `location`), do not overwrite - keep both
    keys under their original names rather than colliding. Use a non-stock
    inventory tool so the stock slimmer does not also fire."""
    raw = json.dumps(
        {
            "data": [
                {
                    "id": "row-1",
                    "location": "Shah Alam",
                    "warehouse": {
                        "id": "wh-1",
                        "warehouse_code": "WH-001",
                    },
                }
            ]
        }
    )

    sanitized = json.loads(
        _sanitize_tool_response("crm_inventory_storage_zones_list", raw)
    )
    row = sanitized["data"][0]

    # `location` survives because target `warehouse` is already taken on this dict.
    assert row["location"] == "Shah Alam"
    assert row["warehouse"]["system_location"] == "WH-001"
