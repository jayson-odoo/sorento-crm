"""Phase 2 RED tests - MCP catalog for the outstanding report (Slice S3).

`documentation/plans/chatbot/PLAN-chatbot-outstanding-report.md` Slice S3;
`documentation/plans/chatbot/chatbot-outstanding-report-acceptance-criteria.md` AC-1120,
AC-1121.

Written before the catalog entries exist. `test_catalog_lists_outstanding_report_tool` must
fail with `StopIteration` (no such tool name in `CATALOG` yet), not an import error -
`test_order_list_tools_expose_new_params` finds its two tools fine (they already exist) and
fails on the missing params.

Note for the coder: `test_catalog_compile.py::test_orders_list_uses_actual_delivery_date_only`
currently asserts `order_date_from`/`order_date_to` are ABSENT from
`crm_order_management_orders_list`'s query_params and description. Adding them here (AC-1121)
will need that assertion reconciled - not this file's job to change, flagging so it is not
missed.
"""
from __future__ import annotations

from sorento_crm_mcp.catalog import CATALOG

NEW_ORDER_LIST_PARAMS = ("customer_query", "order_date_from", "order_date_to", "warehouse_codes")


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
