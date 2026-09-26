"""Sales module bootstrap (PLAN-retail-sales-reports-26sep R4.3, shared with #1260).

`MODULE_KEY` is what `require_module_enabled_with_api_key` gates `/api/v1/sales/*` on and
what the reports kernel checks for the sales report definitions (`module_key = "sales"`).
The module owns the Postgres schema `sales` (created by `sales_s1_reports_module`); this
plan puts no table in it, and #1260's tables will. The sales ORDER data stays in `public`,
owned by `order`: the reports only read it.
"""

MODULE_KEY = "sales"
