import json

from sorento_crm_mcp.server import (
    _sanitize_tool_response,
    _slim_orders_list_row,
)


def _raw_order_row():
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "order_number": "DO-2026-0001",
        "order_date": "2026-06-01T00:00:00",
        "debtor_code": "VB001",
        "debtor_name": "V Bath",
        "created_by": "22222222-2222-2222-2222-222222222222",
        "updated_by": "33333333-3333-3333-3333-333333333333",
        "customer_id": "44444444-4444-4444-4444-444444444444",
        "order_status": {"id": "55555555-5555-5555-5555-555555555555", "status_code": "delivered", "status_name": "Delivered"},
        "lines": [
            {
                "id": "66666666-6666-6666-6666-666666666666",
                "order_id": "11111111-1111-1111-1111-111111111111",
                "product_id": "77777777-7777-7777-7777-777777777777",
                "warehouse_id": "88888888-8888-8888-8888-888888888888",
                "quantity": 2,
                "unit_price": 100.0,
                "product": {
                    "id": "77777777-7777-7777-7777-777777777777",
                    "product_code": "CB1549SS-BL",
                    "product_name": "CB1549SS-BL",
                    "is_discontinued": False,
                },
                "warehouse": {
                    "id": "88888888-8888-8888-8888-888888888888",
                    "warehouse_code": "WH-001",
                    "warehouse_name": "Selangor Main DC",
                },
            }
        ],
    }


def _assert_no_uuid_values(node):
    """No 36-char dashed UUID string anywhere in the payload."""
    if isinstance(node, dict):
        for v in node.values():
            _assert_no_uuid_values(v)
    elif isinstance(node, list):
        for v in node:
            _assert_no_uuid_values(v)
    elif isinstance(node, str):
        assert not (len(node) == 36 and node.count("-") == 4), f"UUID leaked: {node}"


def test_orders_row_drops_all_uuids_and_created_by():
    row = _slim_orders_list_row(_raw_order_row())
    for key in ("id", "created_by", "updated_by", "customer_id"):
        assert key not in row
    line = row["lines"][0]
    for key in ("id", "order_id", "product_id", "warehouse_id"):
        assert key not in line
    assert "id" not in line["product"]
    assert "id" not in line["warehouse"]
    _assert_no_uuid_values(row)


def test_orders_row_keeps_human_identifiers():
    row = _slim_orders_list_row(_raw_order_row())
    assert row["order_number"] == "DO-2026-0001"
    assert row["debtor_name"] == "V Bath"
    assert row["order_status"] == "Delivered"
    line = row["lines"][0]
    assert line["quantity"] == 2
    assert line["product"]["product_code"] == "CB1549SS-BL"
    assert line["warehouse"]["warehouse_code"] == "WH-001"


def test_orders_list_end_to_end_sanitize():
    raw = json.dumps({"data": [_raw_order_row()], "pagination": {"total": 1, "page": 1, "limit": 20}})
    out = json.loads(
        _sanitize_tool_response("crm_order_management_orders_list", raw)
    )
    _assert_no_uuid_values(out["data"])
    assert out["pagination"]["limit"] == 20
