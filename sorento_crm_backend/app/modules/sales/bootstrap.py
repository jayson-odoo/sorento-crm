"""Sales module bootstrap (plan 3.7, owner ruling 26 Sep 06:09, V3; shared with
PLAN-retail-sales-reports-26sep R4.3).

`MODULE_KEY` is what `require_module_enabled_with_api_key` gates `/api/v1/sales/*` on and
what the reports kernel checks for the sales report definitions (`module_key = "sales"`).
The module owns the Postgres schema `sales` (created by `sales_0001_teams`, which holds the
sales teams tables; the reports plan puts no table in it). The sales ORDER data stays in
`public`, owned by `order`: the reports only read it.
"""

MODULE_KEY = "sales"
