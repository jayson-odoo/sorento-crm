# PLAN - Reorder planning per product: one level, one net, order up to the level

Status: **PHASE 2 BUILT** 2026-08-27 (captain's rulings on lane :3080, plan 181ab143). Built on
`feat/scm-uat`; branch `feat/scm-reorder-per-product`. AC-R11..AC-R15 are green under pytest +
vitest (migration `430_plan_row_price_supplier`). NOT yet verified in a browser.
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

## Phase 2 (captain, 27 Aug afternoon; build after the per-product rule lands)

### Suggested level, the industry way
```
ADU          = delivery-order lines' quantity over the study window (90 days, every
               warehouse, cancelled excluded) / 90. The CRM's `orders` / `order_lines` ARE
               the AutoCount delivery-order book (CG-, BRT- series, `sync_source`, a
               warehouse per line), so this is what left the warehouses - what
               `scm.consumption_v` already reads. Ruled 27 Aug after a look at the data:
               DO covers 2,565 products in 90 days against 1,576 for SO lines.
lead_time    = the product's supplier lead time (days); 30 when none is known
safety_stock = ADU x 14 days (ruled 27 Aug)
level        = ADU x lead_time + safety_stock, rounded up to a whole unit
```
Replaces the "avg monthly movement x cover months" suggestion in `scm.reorder_level.
suggested_level` / `suggestion_basis`. The basis JSON names ADU, lead time, safety stock so
the popover can show the three terms. Reorder qty stays `level - net`.

### Product health, by movement only
No margin: costs are often CNY and selling prices MYR, and no exchange rate is trusted.
"Sold" = delivery-order lines in the last 3 months; "bought" = GRN receipts
(`picking_lines.qty_accepted` by `picking_date`, the receipt pickings that roll onto
`purchase_order_lines.qty_received`) in the last 6 months - a receipt, never a purchase
order issued, because a PO is a promise and a GRN is stock in; six months because a 30-90
day lead would otherwise hide a live product. All locations:
- **Fast moving** - sold AND bought in the window.
- **Slow moving** - sold in the window, nothing bought.
- **Dead** - nothing sold and nothing bought, stock on hand > 0 -> "Consider discontinuing".
- **No history** - nothing sold, nothing bought, nothing on hand.
"Purchased N in the last 3 months" on the card reads the same receipts. Net's incoming stays
the PO book (`qty_ordered - qty_received` open) plus unreceived SPO.
The column reads the class and, for Dead, the suggestion. "Margin unknown" goes.

### Price and supplier are the buyer's to change
On the plan row, the Suggested price pill is a switch (Use last price / Ask new price) and
the Suggested supplier is a select over the product's suppliers (`alternatives` on the
recommendation, then every supplier linked to the product). Both ride on the row's decision
(`plan_row_decision`: `price_mode`, `supplier_id`, `unit_cost`) and flow into the draft PO
the plan confirms. Changing the supplier re-reads that supplier's last price and lead time.

### Data joins: what each source may and may not do (captain, 27 Aug: "our DO and GRN are quite disconnected from SO and PO")

| Source | Used for | Never used for |
|---|---|---|
| DO lines (`orders` / `order_lines`) | ADU, "sold" in health | reducing SO outstanding |
| GRN receipts (`picking_lines`) | "bought" in health, receipt lead time | reducing PO open quantity |
| SO book outstanding (AutoCount's own column) | retail demand in net | - |
| PO outstanding book (AutoCount's own figure) | open PO in net | - |
| AutoCount stock snapshot | on hand in net | - |

On hand already reflects every DO and GRN AutoCount booked. Deriving "SO minus our DO" or
"PO minus our GRN" double-counts wherever the join missed (a DO naming no SO line, a GRN the
"Our PO No." matcher tied to the wrong line). Movement sources count movement; the books
say what is outstanding.
