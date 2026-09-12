"""Phase 2 RED tests - MCP catalog for the outstanding report (Slice S3).

`documentation/plans/chatbot/PLAN-chatbot-outstanding-report.md` Slice S3;
`documentation/plans/chatbot/chatbot-outstanding-report-acceptance-criteria.md` AC-1120,
AC-1121.

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

from sorento_crm_mcp.catalog import CATALOG

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
