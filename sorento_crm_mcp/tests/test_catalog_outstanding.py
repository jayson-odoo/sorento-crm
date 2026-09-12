"""Phase 2 RED tests - MCP catalog for the outstanding report (Slice S3 + S4).

`documentation/plans/chatbot/PLAN-chatbot-outstanding-report.md` Slice S3 and "S4 on main"
point 9 / point 5; `documentation/plans/chatbot/chatbot-outstanding-report-acceptance-criteria.md`
AC-1120, AC-1121 (S3) and AC-1113b, AC-1114b (S4).

Written before the catalog entries exist. `test_catalog_lists_outstanding_report_tool` must
fail with `StopIteration` (no such tool name in `CATALOG` yet), not an import error -
`test_order_list_tools_expose_new_params` finds its two tools fine (they already exist) and
fails on the missing params.

AC-1121 (captain ruling, 12 Sep 2026): `order_date_from`/`order_date_to` stay OFF
`crm_order_management_orders_list` and `_by_product_list` - the standing test
`test_catalog_compile.py::test_orders_list_uses_actual_delivery_date_only` is a prior owner
ruling and must stay green. Only `customer_query` and `warehouse_codes` are new on those two
tools; the outstanding-report tool itself still takes `order_date_from`/`order_date_to` (its
own params, asserted separately below - unaffected by this ruling).
"""
from __future__ import annotations

import json

from sorento_crm_mcp.catalog import CATALOG
from sorento_crm_mcp.presenters import _outstanding_detail, present_response

NEW_ORDER_LIST_PARAMS = ("customer_query", "warehouse_codes")


def test_catalog_lists_outstanding_report_tool():
    spec = next(s for s in CATALOG if s.name == "crm_outstanding_report")
    assert spec.path == "/api/v1/order-management/outstanding-report"
    assert spec.method == "GET"
    for param in (
        "product_code", "scope", "customer_query", "warehouse_codes",
        "order_date_from", "order_date_to",
    ):
        assert param in spec.query_params, f"missing query param: {param}"


def test_order_list_tools_expose_new_params():
    for name in ("crm_order_management_orders_list", "crm_order_management_orders_by_product_list"):
        spec = next(s for s in CATALOG if s.name == name)
        for param in NEW_ORDER_LIST_PARAMS:
            assert param in spec.query_params, f"{name} missing query param: {param}"
        # AC-1121 ruling: order_date_* stays OFF these two tools - the DO list keeps
        # actual_delivery_date_* as its only date axis (standing test in
        # test_catalog_compile.py). A coder who adds these here breaks that ruling.
        assert "order_date_from" not in spec.query_params, f"{name} must not gain order_date_from"
        assert "order_date_to" not in spec.query_params, f"{name} must not gain order_date_to"


# --------------------------------------------------------------------- AC-1113b


def test_catalog_exposes_customer_ids_on_outstanding_report():
    """S4 point 9: the resolved customer's id goes as `customer_ids` (csv), ADDED
    alongside `customer_query` (which stays for n8n)."""
    spec = next(s for s in CATALOG if s.name == "crm_outstanding_report")
    assert "customer_ids" in spec.query_params, (
        f"crm_outstanding_report must expose customer_ids: {spec.query_params}"
    )


# --------------------------------------------------------------------- AC-1114b


REPORT_WITH_SO_ROWS = {
    "product_code": "SRTWT7445",
    "customer_name": None,
    "so_rows": [
        {
            "so_number": "SO331785", "customer_name": "Dealer A Sdn Bhd", "location": "BRW-BB",
            "ordered_qty": 410, "transferred_qty": 0, "outstanding_qty": 410, "order_date": "2024-12-20",
        }
    ],
    "do_rows": [],
    # S4 point 5's own signal: the crm_outstanding_report tool passes `detail` through and
    # `present_response` must dispatch on it. This file does not assume WHICH layer
    # stamped it onto the payload (the route's own response, or the MCP compile-tool
    # wrapper) - only that `present_response` reads it here, the same way it already reads
    # `data.get("order_status")` for the `so_outstanding` bucket swap a few lines up.
    "detail": "so",
}


def test_detail_param_renders_outstanding_detail_not_the_report():
    """`detail=so` makes `present_response` render `_outstanding_detail(report, "so")` -
    the numbered SO list - instead of the two-block report `_outstanding_report` builds.
    The route itself is unchanged by `detail` (AC-1114b); this is the PRESENTER dispatch."""
    raw = json.dumps(REPORT_WITH_SO_ROWS)
    rendered = present_response("crm_outstanding_report", raw)
    assert rendered == _outstanding_detail(REPORT_WITH_SO_ROWS, "so"), (
        f"present_response must dispatch to _outstanding_detail when detail is set: {rendered!r}"
    )
    assert "SO331785" in rendered, rendered
    assert "Reply with a number for detail" not in rendered, (
        "the detail list must not also carry the report's own offer footer"
    )
