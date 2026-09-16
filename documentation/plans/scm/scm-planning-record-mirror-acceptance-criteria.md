# UAC - Planning record mirrors every core line on its own (#969)

Plan: `PLAN-scm-planning-record-mirror.md`.

## Journey

CS confirms lines on the fulfilment board for an order whose lines changed in AutoCount after it
was adopted. Every line is confirmable; nobody presses Re-sync. Purchasing sees new lines' demand
as soon as the ingest lands them.

| id | tag | Given / When / Then |
| --- | --- | --- |
| AC-PR1 | [BE] | Given an adopted order and a core line inserted after adoption (no mirror), when the board is read through `GET /fulfilment-planning/board` for that order, then the response carries a `project_line_id` for the late line (no `no_mirror`-shaped null) and a `projects.sales_order_lines` row with `core_sales_order_line_id` = that core line exists; when CS then confirms every line the board returned through `POST /sales-orders/{pso_id}/confirm`, then `lines_undecided == 0` and the supply decision covers the late line. |
| AC-PR2 | [BE] | Given two adopted orders, each with one late core line, when the multi-order board read the FE builds confirm-all from runs over both, then both mirrors exist and both lines carry a `project_line_id`; `POST /fulfilment-planning/confirm-all` then posts both. |
| AC-PR3 | [BE] | Given an adopted order, when `_upsert_lines` receives a payload adding a new SKU, then a mirror line for the new core line exists in the same transaction with `line_no` = previous max + 1. |
| AC-PR3b | [BE] | Given an adopted order, when the ESB push (`POST /api/v1/external/ingest/sales_orders`, `document_ingest_service._sync_lines`) creates a new core line, then a mirror line for it exists in the same transaction with `line_no` = previous max + 1, and the core line carries `source_system = autocount`. |
| AC-PR3c | [BE] | Given an adopted order, when the outstanding book upload (`outstanding_import_service.apply` -> `_write_change`) creates a new core line, then a mirror line for it exists in the same transaction with `line_no` = previous max + 1. |
| AC-PR4 | [BE] | Given an order with no planning record, when `_upsert_lines` adds a new SKU, then no `projects.sales_order_lines` row is created. |
| AC-PR5 | [BE] | Given an adopted order, when one payload removes one line and adds another, then the removed line's empty mirror is pruned (existing behaviour), the added line is mirrored, and the surviving mirrors keep their `line_no`. |
| AC-PR6 | [BE] | Given AC-PR1's order, when the board is read twice, then exactly one mirror line exists per core line (idempotent). |
| AC-PR7 | [BE] | Given a mirror line that already carries a decision or a link, when the ingest runs, then that mirror is untouched (the existing prune rules stand). |
| AC-PR8 | [BE] | Given an adopted order and a late core line, when CS confirms the existing lines directly with no prior board read, then the confirm succeeds for the lines given and no mirror is created for the late line (the heal lives on the read, not the write). |
