# UAC - Planning record mirrors every core line on its own (#969)

Plan: `PLAN-scm-planning-record-mirror.md`.

## Journey

CS confirms lines on the fulfilment board for an order whose lines changed in AutoCount after it
was adopted. Every line is confirmable; nobody presses Re-sync. Purchasing sees new lines' demand
as soon as the ingest lands them.

| id | tag | Given / When / Then |
| --- | --- | --- |
| AC-PR1 | [BE] | Given an adopted order and a core line inserted after adoption (no mirror), when CS confirms that line through `POST /sales-orders/{pso_id}/confirm`, then the response carries no `no_mirror` / unpostable skip for it, a `projects.sales_order_lines` row with `core_sales_order_line_id` = that core line exists, and the supply decision covers the line. |
| AC-PR2 | [BE] | Given two adopted orders, each with one late core line, when `POST /fulfilment-planning/confirm-all` runs over both, then both lines post and both mirrors exist. |
| AC-PR3 | [BE] | Given an adopted order, when `_upsert_lines` receives a payload adding a new SKU, then a mirror line for the new core line exists in the same transaction with `line_no` = previous max + 1. |
| AC-PR4 | [BE] | Given an order with no planning record, when `_upsert_lines` adds a new SKU, then no `projects.sales_order_lines` row is created. |
| AC-PR5 | [BE] | Given an adopted order, when one payload removes one line and adds another, then the removed line's empty mirror is pruned (existing behaviour), the added line is mirrored, and the surviving mirrors keep their `line_no`. |
| AC-PR6 | [BE] | Given AC-PR1's order, when confirm runs twice, then exactly one mirror line exists per core line (idempotent). |
| AC-PR7 | [BE] | Given a mirror line that already carries a decision or a link, when the ingest runs, then that mirror is untouched (the existing prune rules stand). |
