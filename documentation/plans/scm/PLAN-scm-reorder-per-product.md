# PLAN - Reorder planning per product: one level, one net, order up to the level

Status: **PLANNED** 2026-08-27 (captain's rulings on lane :3080, plan 181ab143). Build on `feat/scm-uat`.
UAC: `scm-reorder-per-product-acceptance-criteria.md`.

## The ruling (captain, 27 Aug)

"Our reorder is per product, so it doesn't matter your location, just take the total across all
locations." And: "with our net, we need to reorder up to the reorder level."

Today (`reorder_engine.py`, `reorder_run_service.py`) the manual `reorder_level` policy runs PER
LOCATION: each warehouse carries its own level (`scm.reorder_level.warehouse_id`), and the
AutoCount master level is copied onto every location that has none. Two real rows showed why
that is wrong:

- **SRTWT7408**: AutoCount master level 500, BRW holds 1,296 (overstock). Every empty `-BB` /
  `-IB` bin read "500 - 0 = 500"; nine of them plus 7 of retail need = **4,507 suggested** for a
  product the company is long on.
- **B2155-NL-BLUE**: a level of 12,000 typed into BRW-IB's "Set level" box during the walk
  (`scm.reorder_level`, `source = manual`, 12:21 MYT) drove 11,430 against a net of 570 at that
  one bin, while MWH-BB held 10,860.

## The rule

For each product (not each location):

```
level     = the buyer's override if one is set, else the AutoCount master reorder level
            (scm.reorder_level with warehouse_id IS NULL; per-location rows are IGNORED)
on_hand   = sum of on hand across EVERY location (pools and group bins alike)
incoming  = open PO quantity (all locations) + SPO allocations not yet received (all locations)
demand    = acknowledged / changed project order-inquiry rows, their UNLINKED remainder
          + retail sales-order outstanding quantity (demand_class = retail)
net       = on_hand + incoming - demand
trigger   = net <= level
qty       = level - net             (order UP TO the level), floored at MOQ, rounded up to
                                    the order multiple; 0 when net > level
```

- An awaiting order-inquiry row is not demand (handshake section 3) and is not shown on a tile
  either (hidden 27 Aug).
- A product with NO level (override NULL and master NULL or 0) is `needs_level`, as today: the
  suggestion (avg monthly movement x cover months) is shown, nothing is bought.
- The buy is one line per product. Where it lands (the allocation) is the site pool the demand
  names, BRW by default; the location split is a placement detail, never a second sizing.
- "Cover before buying" (transfer from a pool that holds stock) no longer changes the BUY: with
  one net across locations the stock is already counted. It stays as the transfer proposal on
  the fulfilment board, which is where a move is decided.
- Disposition (overstock / dead) still runs per location; it is about a place.

## The card (Order qty ledger), top to bottom

1. **Project demand** - the acknowledged OI rows: SO number, customer, delivery date, qty,
   linked so far. First, because "what project is asking" is the first question.
2. **Retail demand** - outstanding retail SO lines: SO number, customer, delivery date, qty.
3. **Net now** - on hand (all locations, expandable per location) + PO open + SPO arriving
   - project demand - retail demand = net; the level beside it; gap = level - net.
4. **The buy** - qty, MoQ / multiple applied, supplier, price, cash.
5. **History** - purchases in the last 3 / prior 3 months and the recent-purchases table, last.

## Where

- `app/services/scm/reorder_run_service.py` - the `reorder_level` policy path: aggregate per
  product before the trigger; drop the per-location level copy; demand from `committed_v`
  (acknowledged rows only) + retail SO outstanding.
- `app/services/scm/reorder_engine.py` - `aggregate_network(levels=...)` gains the per-product
  form (one level, not a sum of member levels).
- `scm.reorder_level` - the product-level row (`warehouse_id IS NULL`) is the override; "Set
  level" on the plan writes THAT row. No migration: the column shapes already allow it.
- FE `app/(protected)/scm/reorder/components/PlanOrderQtyLedger.tsx` + `lib/orderQtyLedger.ts`
  - the card order above; `ReorderStatTiles.tsx` - no awaiting tile.

## Out of scope

Forecast policies (`reorder_point` / `periodic_review`) keep their maths. The link horizon and
the pool-only cascade live in `PLAN-scm-oi-handshake.md` section 10.
