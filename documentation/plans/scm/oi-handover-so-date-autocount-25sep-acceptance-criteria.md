# UAC: Order inquiry handover SO DATE is the AutoCount document date (25 Sep 2026)

Plan: `PLAN-oi-handover-so-date-autocount-25sep.md`. AC-SD-n.

## Handover email (`_handover_order_facts`)
- AC-SD-1: An adopted AutoCount order (`published_at` NULL) whose core `sales_orders.order_date`
  is 2026-09-18 and whose project SO `created_at` is 2026-09-23 prints `so_date`
  `18/09/2026` on every handover line for that order.
- AC-SD-2: A published (authored) order with `order_date` set on its core SO prints the
  core `order_date`, not `published_at`.
- AC-SD-3: An order whose core SO has `order_date` NULL falls back to `published_at`, then
  `created_at` (today's behaviour preserved).
- AC-SD-4: An order with no core SO (`so_id` NULL, a draft) still prints `published_at or
  created_at`; nothing raises.

## OI rows (`serialize_rows` via `list_rows`)
- AC-SD-5: The same adopted order's OI rows carry `so_date` = the core `order_date`
  (2026-09-18), not the project SO `created_at`.
- AC-SD-6: Fallback order for rows is identical to AC-SD-3 / AC-SD-4.

## Regression
- AC-SD-7: `tests/test_order_inquiry_handover_automation.py` and the OI row/list tests stay
  green; existing fixtures that never set `order_date` keep their asserted `so_date`.
- AC-SD-8: `order_inquiry_header_service` and `order_inquiry_worklist_service` are untouched
  (diff shows no change there).
