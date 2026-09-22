# UAC: Start Plan pre-selects orders raised in a window (22 Sep 2026)

Plan: `PLAN-reorder-plan-raised-filter.md`. AC-RF-n.

- AC-RF-1: `GET /scm/reorder-runs/candidate-orders` accepts `raised_from` and `raised_to`
  (dates, optional) and every returned order carries `rows_raised_in_window`.
- AC-RF-2: `rows_raised_in_window` counts the order's candidate rows whose first upload day
  (`order_inquiry_rows.created_at`) falls inside the window, bounds inclusive, an omitted
  bound open; with both omitted it equals `rows_total`.
- AC-RF-3: An order with zero rows in the window is still listed (the window never removes
  an order from the list).
- AC-RF-4: `rows_in_range`, `rows_awaiting`, `rows_total` are unaffected by the raise window.
- AC-RF-5: Start Plan shows "Inquiries raised" From / To only while Demand = Project.
- AC-RF-6: With a window set, the pre-selected orders are exactly those with
  `rows_in_range > 0` and `rows_raised_in_window > 0`; clearing the window restores today's
  pre-selection; a list the buyer has touched is never re-derived.
- AC-RF-7: The service sends `raised_from` / `raised_to` as query params and the query key
  includes them, so editing the window refetches.
- AC-RF-8: Existing candidate-orders and modal tests stay green.
- AC-RF-9 (browser, once a slot frees): Demand = Project, raised 17/09 to 18/09, delivery to
  31/10: the picker pre-selects only the orders with rows uploaded on those days.
