import json

from sorento_crm_mcp.server import (
    GRN_LIST_LIMIT_CAP,
    GRN_LIST_LIMIT_DEFAULT,
    _coerce_grn_limit,
    _sanitize_tool_response,
    _slim_grn_response,
)


def _raw_grn_row():
    return {
        "id": "grn-1",
        "picking_number": "GRN-0001",
        "picking_date": "2026-01-15",
        "picking_type": "goods_received",
        "picking_status": "received",
        "inspection_status": "pending",
        "inspection_date": None,
        "inspected_by_user_id": None,
        "quality_remarks": None,
        "source_entity_type": "spo",
        "source_entity_id": "src",
        "picked_by_user_id": "u1",
        "total_items_picked": 10,
        "total_items_discrepancy": 0,
        "total_cost": 100.0,
        "spo_number": "SPO-1",
        "notes": "ok",
        "picking_lines": [],
        "lines_count": 3,
        "created_at": "2026-01-15T00:00:00",
        "updated_at": "2026-01-15T00:00:00",
    }


def test_grn_list_response_is_trimmed_and_renamed():
    raw = json.dumps({"data": [_raw_grn_row()], "pagination": {"total": 1, "page": 1, "limit": 50}})
    out = json.loads(_sanitize_tool_response("crm_procurement_grn_list", raw))
    row = out["data"][0]

    assert row["document_number"] == "GRN-0001"
    assert row["receiving_date"] == "2026-01-15"
    for key in (
        "picking_number",
        "picking_date",
        "picking_status",
        "picking_type",
        "inspection_status",
        "inspection_date",
        "inspected_by_user_id",
        "quality_remarks",
        "source_entity_type",
        "source_entity_id",
        "picked_by_user_id",
        "total_items_picked",
        "total_items_discrepancy",
        "total_cost",
    ):
        assert key not in row, f"{key} should be dropped"
    for key in (
        "document_number",
        "spo_number",
        "receiving_date",
        "notes",
        "picking_lines",
        "lines_count",
        "created_at",
        "updated_at",
    ):
        assert key in row


def test_grn_get_response_is_also_trimmed():
    raw = json.dumps(_raw_grn_row())
    out = json.loads(_sanitize_tool_response("crm_procurement_grn_get", raw))
    assert out["document_number"] == "GRN-0001"
    assert "picking_status" not in out


def test_slim_grn_response_preserves_rename_collision():
    row = _raw_grn_row()
    row["document_number"] = "MANUAL"
    out = _slim_grn_response({"data": [row]})
    assert out["data"][0]["document_number"] == "MANUAL"
    assert out["data"][0].get("picking_number") == "GRN-0001"


def test_coerce_grn_limit_defaults_and_caps():
    assert _coerce_grn_limit(None) == GRN_LIST_LIMIT_DEFAULT
    assert _coerce_grn_limit("") == GRN_LIST_LIMIT_DEFAULT
    assert _coerce_grn_limit("abc") == GRN_LIST_LIMIT_DEFAULT
    assert _coerce_grn_limit("0") == GRN_LIST_LIMIT_DEFAULT
    assert _coerce_grn_limit("25") == 25
    assert _coerce_grn_limit("500") == GRN_LIST_LIMIT_CAP
    assert _coerce_grn_limit(GRN_LIST_LIMIT_CAP + 1) == GRN_LIST_LIMIT_CAP
