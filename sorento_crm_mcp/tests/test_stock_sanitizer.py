import json

from sorento_crm_mcp.server import _sanitize_stock_tool_response


def test_stock_tool_response_hides_non_on_hand_quantities_and_normalizes_updated_at():
    raw = json.dumps(
        {
            "data": [
                {
                    "id": "stock-1",
                    "quantity_on_hand": 12,
                    "quantity_available": 10,
                    "quantity_reserved": 2,
                    "quantity_damaged": 1,
                    "status": "normal",
                    "updated_at": "2026-03-01T00:00:00",
                    "product": {"product_code": "SKU-1"},
                }
            ],
            "pagination": {"total": 1, "page": 1, "limit": 50},
        }
    )

    sanitized = json.loads(
        _sanitize_stock_tool_response("crm_inventory_stock_balance_list", raw)
    )
    row = sanitized["data"][0]

    assert row["quantity_on_hand"] == 12
    assert row["updated_at"] == "2026-03-01T08:00:00+08:00"
    assert "quantity_available" not in row
    assert "quantity_reserved" not in row
    assert "quantity_damaged" not in row
    assert "status" not in row


def test_non_stock_tool_response_is_not_changed():
    raw = json.dumps({"quantity_available": 10})

    assert _sanitize_stock_tool_response("crm_master_products_list", raw) == raw
