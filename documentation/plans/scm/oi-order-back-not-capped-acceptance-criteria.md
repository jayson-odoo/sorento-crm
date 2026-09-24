# UAC: ORDER BACK rows are owed in full (22 Sep 2026)

Plan: `PLAN-oi-order-back-not-capped.md`. AC-OB-n.

## Reader
- AC-OB-1: A sheet row whose Remark cell contains "order back" (case-insensitive, any
  whitespace between the words) reads `order_back=True`; its `delivery_date` is the date in
  the Delivery date cell.
- AC-OB-2: A sheet row whose Delivery date cell reads "ORDER BACK" still reads
  `order_back=True` with `delivery_date=None` (unchanged).
- AC-OB-3: A row with neither reads `order_back=False`.

## Owed quantity
- AC-OB-4: `scm.committed_v` counts an ORDER_BACK row of qty 3 whose core line is delivered
  3/3 as `project_qty` 3 (and `project_confirmed_qty` 3 on the confirmed leg) at the
  warehouse named by the row's `stock_location`.
- AC-OB-5: An ORDER row on that same delivered line counts 0 (the 14 Sep cap is unchanged).
- AC-OB-6: An ORDER_BACK row with 1 linked and 1 bundled of qty 3 counts 1.
- AC-OB-7: `horizon_committed_select_sql` (the plan's own SELECT) returns the same figures
  as AC-OB-4/5 for the same rows.
- AC-OB-8: The worklist's Remaining for an ORDER_BACK row on a delivered line is the row's
  qty less linked less bundled, not 0.
- AC-OB-9: `/reorder-runs/candidate-orders` lists an SO whose only inquiry row is an
  ORDER_BACK on a delivered line, `rows_total` 1.

## Importer
- AC-OB-10: Uploading a sheet row marked ORDER BACK (remark or date cell) against a line
  delivered in full stores verb `ORDER_BACK`, state `raised`, `actioned_at` NULL.
- AC-OB-11: Uploading an ORDER row against a line delivered in full still stores state
  `actioned` with `actioned_at` set (AC-S1-29 stands).

## Migration
- AC-OB-12: `alembic upgrade head` then `downgrade -1` round-trips `scm.committed_v`; the
  drift guard in `test_committed_v_migration_chain.py` passes against the new body.

## Backfill script
- AC-OB-13: Dry run prints each candidate flip (SO, item, qty, location) and writes nothing.
- AC-OB-14: `--apply` flips an ORDER row with `actioned_at == order_inquiries.raised_at`
  whose matching sheet row reads ORDER BACK to `ORDER_BACK` / `raised`, `actioned_by` and
  `actioned_at` NULL, and sets the inquiry header state to `raised`.
- AC-OB-15: A row a person marked actioned (`actioned_at` differs from `raised_at`) is never
  flipped, even when its sheet row reads ORDER BACK.
- AC-OB-16: A sheet row with no matching inquiry row is reported as unmatched, not created.

## Browser (once a slot frees)
- AC-OB-17: Start Plan, Demand = Project, search SO417310 on a DB where the row is
  ORDER_BACK / raised: the order is listed; Start Plan produces a Buy of 3 for MKT5529SS-DIY
  at BRW-BB.
