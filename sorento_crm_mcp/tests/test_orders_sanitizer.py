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
        "estimated_delivery_date": "2026-06-03",
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
    assert "estimated_delivery_date" not in row
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


def test_grouped_orders_list_group_rows_are_slimmed_like_the_flat_rows():
    """CHAT-GROUPED-ORDER-STATUS: `group_by` buckets the route's raw rows into
    `groups[i].rows`. Those rows must come out exactly like the flat `data` rows (Status
    as text, no UUIDs): a raw `order_status` dict reached the presenter and crashed the
    chat turn (`TypeError: unhashable type: 'dict'`)."""
    row = {**_raw_order_row(), "debtor_name": "CUSTOMER A", "company_id": "99999999-9999-9999-9999-999999999999"}
    raw = json.dumps(
        {
            "data": [row],
            "groups": [{"key": "CUSTOMER A", "label": "CUSTOMER A", "rows": [row]}],
            "pagination": {"total": 1, "page": 1, "limit": 20},
        }
    )
    out = json.loads(_sanitize_tool_response("crm_order_management_orders_list", raw))
    (group,) = out["groups"]
    assert group["key"] == "CUSTOMER A" and group["label"] == "CUSTOMER A"
    (grouped,) = group["rows"]
    assert grouped["order_status"] == "Delivered"
    assert grouped == out["data"][0]
    _assert_no_uuid_values(out["groups"])


def test_so_outstanding_rows_keep_their_plain_text_customer_flat_and_grouped():
    """The `customer` drop is for the DO row's embedded customer OBJECT. An SO-outstanding
    row's `customer` is the plain-text name (`order_service.so_outstanding_rows`) the
    presenter prints as Customer, so it survives the trim, in `data` and in group rows."""
    so_row = {
        "so_number": "SO-ZZT-1",
        "product_id": "77777777-7777-7777-7777-777777777777",
        "product_code": "ZZT5733",
        "outstanding_qty": 4,
        "order_date": "2026-09-20",
        "customer": "CUSTOMER A",
    }
    raw = json.dumps(
        {
            "data": [so_row],
            "order_status": "so_outstanding",
            "groups": [{"key": "ZZT5733", "label": "ZZT5733", "rows": [so_row]}],
        }
    )
    out = json.loads(_sanitize_tool_response("crm_order_management_orders_list", raw))
    assert out["data"][0]["customer"] == "CUSTOMER A"
    assert out["groups"][0]["rows"][0]["customer"] == "CUSTOMER A"
    do_row = _slim_orders_list_row({**_raw_order_row(), "customer": {"id": "x", "customer_name": "CUSTOMER A"}})
    assert "customer" not in do_row
