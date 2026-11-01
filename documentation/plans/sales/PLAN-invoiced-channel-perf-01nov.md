# PLAN: Invoiced tab Channel column fast (set-based), same figures

Status: in review, PR #2071 (small fix track: no migration, no auth/RBAC change, no new ingest surface)

Lane: INVOICED-CHANNEL-PERF. UAC: `invoiced-channel-perf-01nov-acceptance-criteria.md`.

## Problem

Sales & outstanding > Invoiced asks for every detail column (`ReportPage.tsx` sends an empty
`detail.columns`, which means the whole catalog). The Channel column (the per-line sales type,
`app/services/sales/invoiced_sales.py` `sales_type_label()`) takes minutes on a real-size month while
every other column takes seconds.

## Cause (confirmed on a synthetic seed with EXPLAIN ANALYZE)

1. `sales_type_label()` builds `CASE WHEN st = 'dealer' ... WHEN st = 'project' ...` over the
   `sales_type()` expression, so the whole sales type subquery is inlined once per WHEN (7 times);
   Postgres does not share them, so a line whose type is late in the list runs it up to 7 times.
2. `_sales_order_class_kind()` scans `sales_orders` and tests each row with `so.id IN (traced ids)`,
   so every evaluation reads the whole sales order table rather than looking up the few orders the
   document traces to.
3. The resulting planner cost is far above `jit_above_cost`, so Postgres JIT-compiles the query:
   even after 1 and 2, the compile took about 5 s of a month's run while execution took 0.3 s.

## Fix

- The label is a simple `CASE <value> WHEN ...`, the value computed once.
- The class kind aggregates over the traced ids joined to `sales_orders` (index lookups), the
  inherited fallback (a note with no traced line takes its invoice's orders) kept as is.
- The report engine runs its statements with `SET LOCAL jit = off` (`engine._unscoped`, the one
  context every engine entry uses).
- Same rules, same values: an equality test pins old vs new expression on a seeded sample.
- `scripts/time_invoiced_channel.py` times one day and one month, all columns vs Channel only.

## Side finding

Asking for `customers`, `orders` or `products` alone as detail columns: check for a 500 on main and
report; fix only if it is the same code path and small.
