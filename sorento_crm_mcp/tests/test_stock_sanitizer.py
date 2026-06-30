import json

from sorento_crm_mcp.server import _sanitize_tool_response


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
        _sanitize_tool_response("crm_inventory_stock_balance_list", raw)
    )
    row = sanitized["data"][0]

    assert row["quantity_on_hand"] == 12
    assert row["updated_at"] == "2026-03-01T08:00:00"
    assert "quantity_available" not in row
    assert "quantity_reserved" not in row
    assert "quantity_damaged" not in row
    assert "status" not in row


def test_non_stock_tool_response_normalizes_updated_at():
    """Every MCP tool — not just stock — must rewrite updated_at to Malaysia time."""
    raw = json.dumps(
        {
            "data": [
                {
                    "id": "prod-1",
                    "product_code": "SKU-1",
                    "quantity_available": 10,
                    "updated_at": "2026-03-01T00:00:00",
                }
            ],
            "pagination": {"total": 1, "page": 1, "limit": 50},
        }
    )

    sanitized = json.loads(
        _sanitize_tool_response("crm_master_products_list", raw)
    )
    row = sanitized["data"][0]

    assert row["updated_at"] == "2026-03-01T08:00:00"
    # Non-stock tools keep their full payload; nothing is stripped.
    assert row["quantity_available"] == 10


def test_nested_updated_at_is_normalized_for_non_stock_tool():
    """Recursive walker must reach updated_at nested inside related objects."""
    raw = json.dumps(
        {
            "data": [
                {
                    "id": "promo-1",
                    "updated_at": "2026-03-01T00:00:00Z",
                    "product": {
                        "id": "prod-1",
                        "updated_at": "2026-04-15T12:30:00",
                    },
                    "attachments": [
                        {
                            "id": "att-1",
                            "updated_at": "2026-05-01T01:00:00",
                        }
                    ],
                }
            ]
        }
    )

    # promotion_ids present -> NOT browse mode, so the inline attachments
    # survive the browse-mode strip and the walker must normalize them too.
    sanitized = json.loads(
        _sanitize_tool_response(
            "crm_marketing_promotions_list",
            raw,
            query={"promotion_ids": ["promo-1"]},
        )
    )
    row = sanitized["data"][0]

    assert row["updated_at"] == "2026-03-01T08:00:00"
    assert row["product"]["updated_at"] == "2026-04-15T20:30:00"
    assert row["attachments"][0]["updated_at"] == "2026-05-01T09:00:00"


def test_response_is_unchanged_when_no_updated_at_present():
    raw = json.dumps({"quantity_available": 10})
    assert _sanitize_tool_response("crm_master_products_list", raw) == raw


def test_invalid_json_falls_through_unchanged():
    raw = "not-json"
    assert _sanitize_tool_response("crm_master_products_list", raw) == raw
