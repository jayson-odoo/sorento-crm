"""Project row slimming (self-review finding, 2026-07-28).

`crm_projects_list` shipped returning the FE's full 50-field project row: ten internal UUIDs,
`can_edit` (a permission answer for a browser, meaningless to an agent), and both halves of
every id/name pair. Two costs, and neither is hypothetical:

* **the agent quotes UUIDs.** Every other list tool drops its UUID-bearing keys for exactly
  this reason (`crm_marketing_promotions_list` drops `id`, `created_by`), because the chat and
  WhatsApp surfaces must never show one.
* **tokens.** 50 fields x 25 rows of mostly-null internal plumbing, on a tool the agent calls
  before almost every project answer.

`id` is the deliberate exception: `crm_project_detail` and `crm_project_quotations_list` both
need it, so it stays while its nine siblings go.
"""
from __future__ import annotations

import json

from sorento_crm_mcp.server import _sanitize_tool_response

_ROW = {
    "id": "11111111-1111-1111-1111-111111111111",
    "project_code": "PRJ-000142",
    "title": "Residensi Damai Phase 1",
    "outcome": "open",
    "loss_reason": None,
    "developer_party_id": "22222222-2222-2222-2222-222222222222",
    "developer_name": "Damai Land Sdn Bhd",
    "type_id": "33333333-3333-3333-3333-333333333333",
    "type_name": "Property Development",
    "template_id": "44444444-4444-4444-4444-444444444444",
    "template_name": "Property Development",
    "lead_id": None,
    "lead_code": None,
    "lead_owner_user_id": "55555555-5555-5555-5555-555555555555",
    "status_id": "66666666-6666-6666-6666-666666666666",
    "status_key": "quoted",
    "status_label": "Quoted",
    "owner_user_id": "77777777-7777-7777-7777-777777777777",
    "owner_name": "Ali",
    "architect_party_id": "88888888-8888-8888-8888-888888888888",
    "architect_name": "Arkitek ABC",
    "main_contractor_party_id": "99999999-9999-9999-9999-999999999999",
    "main_contractor_name": "Builder Bhd",
    "brands": ["Sorento"],
    "brand_ids": ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"],
    "estimated_sales_value": "500000.00",
    "stale_level": 2,
    "is_unattended": False,
    "can_edit": True,
    "management_notes": "chasing the architect",
    "updated_at": "2026-07-27T10:00:00",
}


def _sanitize(tool: str, payload) -> dict:
    """The sanitizer takes and returns a JSON STRING -- pass a dict and it silently returns it
    untouched, which is how the first version of this test "passed" against unslimmed rows."""
    return json.loads(_sanitize_tool_response(tool, json.dumps(payload), {}))


def _sanitized(tool="crm_projects_list", row=None):
    return _sanitize(tool, {"data": [dict(row or _ROW)], "pagination": {"total": 1}})


def test_internal_uuids_are_dropped_but_the_project_id_survives():
    row = _sanitized()["data"][0]
    assert row["id"] == _ROW["id"], "the agent needs this to call crm_project_detail"
    for key in (
        "developer_party_id",
        "type_id",
        "template_id",
        "lead_owner_user_id",
        "status_id",
        "owner_user_id",
        "architect_party_id",
        "main_contractor_party_id",
        "brand_ids",
    ):
        assert key not in row, f"{key} leaked a UUID into a chat-facing payload"


def test_the_human_readable_half_of_every_pair_is_kept():
    row = _sanitized()["data"][0]
    for key in (
        "project_code",
        "title",
        "developer_name",
        "type_name",
        "status_key",
        "status_label",
        "owner_name",
        "brands",
        "estimated_sales_value",
        "stale_level",
    ):
        assert key in row, f"{key} is what the agent answers with; it must survive"


def test_browser_only_fields_are_dropped():
    """`can_edit` answers "should this button render", which no agent can act on."""
    assert "can_edit" not in _sanitized()["data"][0]


def test_the_detail_tool_is_slimmed_the_same_way():
    """One project, same rule -- otherwise the same field is a UUID in one tool and absent in
    the other, and the agent learns to quote whichever it saw last."""
    payload = _sanitize("crm_project_detail", dict(_ROW))
    assert payload["id"] == _ROW["id"]
    assert "owner_user_id" not in payload
    assert payload["owner_name"] == "Ali"


def test_slimming_leaves_other_tools_alone():
    row = {"id": "x", "owner_user_id": "keep-me"}
    payload = _sanitize("crm_complaints_list", {"data": [row]})
    assert payload["data"][0]["owner_user_id"] == "keep-me"


def test_pagination_and_envelope_survive():
    payload = _sanitized()
    assert payload["pagination"]["total"] == 1
    assert isinstance(payload["data"], list)


_QUOTATION_ROW = {
    "id": "c1c1c1c1-c1c1-c1c1-c1c1-c1c1c1c1c1c1",
    "project_id": "11111111-1111-1111-1111-111111111111",
    "quotation_number": "PQ-000031",
    "series_name": "Bathroom package",
    "outcome": "open",
    "loss_reason_label": None,
    "current_version_id": "d2d2d2d2-d2d2-d2d2-d2d2-d2d2d2d2d2d2",
    "current_version_no": 3,
    "current_total": "182000.00",
    "issued_by": "77777777-7777-7777-7777-777777777777",
    "issued_by_name": "Ali",
    "below_floor_count": 1,
    "line_count": 12,
    "updated_at": "2026-07-27T10:00:00",
}


def test_the_quotations_list_drops_its_internal_uuids_too():
    """Same rule, same reason -- and the same slice shipped both tools. A quotation row carries
    `project_id` (which the caller just passed in), `current_version_id` (nothing consumes it)
    and `issued_by` beside the `issued_by_name` the agent should be quoting.
    """
    out = _sanitize("crm_project_quotations_list", {"data": [_QUOTATION_ROW]})
    row = out["data"][0]

    for dropped in ("project_id", "current_version_id", "issued_by"):
        assert dropped not in row, f"{dropped} survived into the agent's context"
    # The readable halves stay, including the ones the agent reasons about.
    assert row["quotation_number"] == "PQ-000031"
    assert row["issued_by_name"] == "Ali"
    assert row["current_version_no"] == 3
    assert row["current_total"] == "182000.00"
    assert row["below_floor_count"] == 1


def test_the_quotation_id_stays_because_the_agent_has_to_name_the_quotation():
    """It is the only handle on a specific quotation: an answer about "the bathroom package
    quotation" has to be able to come back to the same row on the next turn."""
    out = _sanitize("crm_project_quotations_list", {"data": [_QUOTATION_ROW]})
    assert out["data"][0]["id"] == _QUOTATION_ROW["id"]
