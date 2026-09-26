"""Phase 2 RED tests - MCP catalog entry for the top selling ranking (S3).

`documentation/plans/chatbot/PLAN-chatbot-top-x-hot-selling-24sep.md` slice S3;
`chatbot-top-x-hot-selling-24sep-acceptance-criteria.md` AC-1940, with the params
the owner's 26 Sep 2026 rulings on PR #1175 gave the route: `rank_by` (required),
`basis`, `group`, `n` (no page / page_size: paging is banned).

The presenter wiring (`present_response("crm_top_selling_report", ...)`) is S1's,
not asserted here. The backend halves (the order domain claiming the tool, the
read-only allow-list, `mcp_tool_domains`, `FIELD_REVEAL_KEYS`) are asserted by the
backend's own guardrail tests.
"""
from __future__ import annotations

from sorento_crm_mcp.catalog import CATALOG

TOOL = "crm_top_selling_report"

REQUIRED_QUERY_PARAMS = (
    "rank_by",
    "basis",
    "group",
    "n",
    "customer_ids",
    "customer_query",
    "category_ids",
    "sales_agent_ids",
    "channel",
    "date_from",
    "date_to",
    "contact_id",
    "space_id",
    "detail_code",
    "count_only",
)


def _spec():
    return next(s for s in CATALOG if s.name == TOOL)


def test_catalog_lists_top_selling_tool() -> None:
    spec = _spec()
    assert spec.path == "/api/v1/order-management/top-selling", spec.path
    assert spec.method == "GET", spec.method
    assert spec.domain == "orders", spec.domain
    assert spec.restricted_fields == (("sales_orders.sales_report", "Sales report"),), (
        "same reveal key as the sales report, no new key: "
        f"{spec.restricted_fields}"
    )
    missing = [p for p in REQUIRED_QUERY_PARAMS if p not in spec.query_params]
    assert not missing, f"{TOOL} missing query params: {missing} (has {spec.query_params})"


def test_no_paging_params() -> None:
    """Owner ruling (26 Sep 01:50Z): no paging, no 'more'."""
    spec = _spec()
    for banned in ("page", "page_size", "limit", "offset", "top_n"):
        assert banned not in spec.query_params, banned


def test_description_states_the_required_metric_and_the_no_cutoff_rule() -> None:
    text = _spec().description
    assert "rank_by" in text and "REQUIRED" in text
    assert "total_count" in text
    assert chr(0x2013) not in text and chr(0x2014) not in text
