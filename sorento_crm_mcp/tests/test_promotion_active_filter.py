"""_filter_active_promotion_records: list rows pass through, drill-downs stay active-only.

Director requirement: promotions list must surface expired promotions (backend
fallback rows carry is_expired=true) so the agent answers "found but expired".
Drill-down tools (get / products / attachments) keep the active-only block.
"""
import json

from sorento_crm_mcp.server import (
    PROMOTION_TOOL_NAMES,
    _filter_active_promotion_records,
)

INACTIVE_ROW = {
    "id": "26ff9ed1-2f21-44db-a9bb-bded38ea110d",
    "description": "_SORENTO A3 FLYER 2025-2026_compressed",
    "is_active": False,
    "is_expired": True,
}
ACTIVE_ROW = {
    "id": "11111111-1111-1111-1111-111111111111",
    "description": "LIVE PROMO",
    "is_active": True,
    "is_expired": False,
}


def _list_payload(*rows):
    return json.dumps(
        {
            "data": list(rows),
            "pagination": {"total": len(rows), "page": 1, "limit": 10},
            "empty": not rows,
            "fallback_used": True,
        }
    )


def test_promotions_list_not_in_filtered_tool_names():
    assert "crm_marketing_promotions_list" not in PROMOTION_TOOL_NAMES


def test_promotions_list_keeps_inactive_fallback_rows():
    raw = _list_payload(INACTIVE_ROW)
    out = _filter_active_promotion_records("crm_marketing_promotions_list", raw)
    data = json.loads(out)
    assert len(data["data"]) == 1
    assert data["data"][0]["is_expired"] is True


def test_promotions_get_still_blocks_inactive():
    raw = json.dumps(INACTIVE_ROW)
    out = _filter_active_promotion_records("crm_marketing_promotions_get", raw)
    assert json.loads(out)["code"] == "PROMOTION_INACTIVE"


def test_promotion_products_list_still_drops_inactive_promotion_rows():
    raw = _list_payload(
        {"id": "row-1", "promotion": INACTIVE_ROW},
        {"id": "row-2", "promotion": ACTIVE_ROW},
    )
    out = _filter_active_promotion_records(
        "crm_marketing_promotion_products_list", raw
    )
    data = json.loads(out)
    assert [r["id"] for r in data["data"]] == ["row-2"]
