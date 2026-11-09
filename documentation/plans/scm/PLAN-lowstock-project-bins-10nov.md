# PLAN: low stock per-location columns count ticked project bins

Status: in progress (small fix track: under 300 lines, no migration, no auth/RBAC change)

Lane: LOWSTOCK-PROJECT-BINS. Follow-up of #2293 (LOWSTOCK-LASTIN-LOCATION,
`PLAN-lowstock-lastin-location-09nov.md`, merged c488fcfd).

## Journey

Owner ruling 10 Nov 2026 ~00:35, question (a) "yes": in Reorder Planning > Start Plan, a
PROJECT BIN the user ticks as one of the plan's locations (BRW-IB, BRW-BB) counts in the low
stock report's per-location columns like any other ticked location. The rule is literal:
every location the run selected counts, and nothing outside them.

Columns: Last in qty / Last in date (one receipt, summed within the run's locations, the #2293
tie-break), BRW on hand, BRW PO qty, BRW incoming qty.

## Where #2293 filters to site pool (before this lane)

| Place | Column | Decision |
|---|---|---|
| `summary_order_service.report_warehouse_ids` (`summary_order_service.py:917`) | the ONE shared set every column reads | Drop the site-pool predicate: the run's `warehouse_ids` as-is (the ORM query stays, so the company scope still applies). |
| `summary_order_service._pool_on_hand_map` (`:948`) | BRW on hand | Site-pool predicate only when no run scope is given (None, `stock_debt_service`'s network-wide reading). With a scope, the scope decides. `counts_as_available` stays (an availability rule, not a location rule). |
| `site_pool_supply.open_po_by_product` (`site_pool_supply.py`, `AND {ACTIVE_SITE_POOL_SQL}`) | BRW PO qty | Same: site-pool predicate only when `warehouse_ids is None`. |
| `site_pool_supply.open_spo_by_product` (`active_site_pool_sql("warehouses")`) | BRW incoming qty | Same. |
| `spo_last_receipt_service.last_in_map` | Last in qty / date | No site-pool filter of its own; it already reads only the ids it is handed, so it follows the shared set. |

One shared location filter stays: `report_warehouse_ids(run)`.

## Unchanged

- A BRW-only run: no project bin in its scope, so every column reads exactly as before.
- The daily low stock job: its run is created from its own `warehouse_codes`, none of them
  project bins, so its scope is unchanged.
- Every network-wide caller (warehouse_ids None) keeps the site-pool rule.

## Risk: a run with no location ticked

`reorder_run_service._resolve_warehouse_ids` (`reorder_run_service.py:286-293`) stamps EVERY
active warehouse, project bins included, when no codes are given: a Start Plan with nothing
ticked, or a scheduled low stock job with empty `warehouse_codes` (`task_scheduler.py:538`,
"empty = all active"). Under the literal rule those bins are now selected, so they count.
Raised to the owner as a crew-ask; the daily job is unchanged only if its config lists codes.

## Tests (red first, `tests/scm/test_lowstock_run_locations.py`)

1. A BRW + BRW-IB run: a newer BRW-IB receipt wins Last in (SRTWCX7405-RL-S-PJ shape: BRW-IB
   20/10 line, container YMMU6026231).
2. A BRW + BRW-IB run: BRW-IB stock, open PO and open SPO count in on hand, PO qty, incoming.
3. A BRW-only run with the same data: unchanged (BRW figures only).
4. The daily job's run: unchanged (project bin outside its codes never counts).
5. The #2293 test that pinned "a project bin never answers Last in even when ticked" flips:
   the ticked BRW-BB lines now sum into the receipt.
