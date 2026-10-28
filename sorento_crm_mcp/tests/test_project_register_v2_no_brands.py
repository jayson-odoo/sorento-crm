"""PROJECT-REGISTER-V2 UAC G5: the project tools keep working when the backend response has no
brand fields (brands are removed from the project API). Written fresh; the older sanitizer tests
are untouched."""
from __future__ import annotations

import json

from sorento_crm_mcp.server import _sanitize_tool_response

_ROW = {
    "id": "11111111-1111-1111-1111-111111111111",
    "project_code": "PRJ-000142",
    "title": "CONTOH Residensi Damai Phase 1",
    "outcome": "open",
    "developer_party_id": "22222222-2222-2222-2222-222222222222",
    "developer_name": "CONTOH Damai Land Sdn Bhd",
    "owner_user_id": "77777777-7777-7777-7777-777777777777",
    "owner_name": "Sales A",
    "status_label": "Quoted",
    "can_edit": True,
}


def _sanitize(tool: str, payload) -> dict:
    return json.loads(_sanitize_tool_response(tool, json.dumps(payload), {}))


def test_the_project_list_tool_slims_a_row_that_has_no_brand_fields():
    row = _sanitize("crm_projects_list", {"data": [dict(_ROW)], "pagination": {"total": 1}})["data"][0]
    assert row["id"] == _ROW["id"]
    assert row["developer_name"] == _ROW["developer_name"] and row["owner_name"] == "Sales A"
    for gone in ("developer_party_id", "owner_user_id", "can_edit"):
        assert gone not in row
    assert "brands" not in row and "brand_ids" not in row


def test_the_project_detail_tool_slims_a_row_that_has_no_brand_fields():
    row = _sanitize("crm_project_detail", dict(_ROW))
    assert row["project_code"] == "PRJ-000142" and "owner_user_id" not in row
    assert "brands" not in row and "brand_ids" not in row
