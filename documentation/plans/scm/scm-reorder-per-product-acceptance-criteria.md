# UAC - Reorder planning per product

Plan: `PLAN-scm-reorder-per-product.md`. Every criterion is pinned by a pytest (engine / run
service) or a vitest (ledger card); the two named rows are the browser proof on :3080.

- **AC-R1 one net per product.** GIVEN SRTWT7408 with 1,296 on hand at BRW, 0 at nine group
  bins, master level 500, 7 retail outstanding, no acknowledged OI rows WHEN a manual plan runs
  THEN net = 1,289, the product is NOT triggered, suggested qty = 0, and no row reads 500 for a
  bin.
- **AC-R2 order up to the level.** GIVEN level 12,000 (product override), on hand 10,860 +
  0 + 0, PO open 860, SPO 0, project demand 150, retail 290 THEN net = 11,280, gap = 720,
  qty = 720 (before MoQ / multiple).
- **AC-R3 per-location levels are ignored.** GIVEN a `scm.reorder_level` row with a
  `warehouse_id` and a level of 12,000 and no product-level override THEN the plan uses the
  AutoCount master level, and the card names the source ("AutoCount master" / "buyer level").
- **AC-R4 awaiting is not demand.** GIVEN an awaiting OI row of 100 and an acknowledged one of
  20 THEN demand counts 20; the tile "Awaiting acknowledgement" is not rendered.
- **AC-R5 linked remainder only.** GIVEN an acknowledged OI row of 50 linked 30 to a PO THEN
  project demand counts 20 and the PO's open quantity counts in incoming once.
- **AC-R6 MoQ and multiple.** GIVEN gap 720, MoQ 1,000, multiple 100 THEN qty = 1,000; GIVEN
  gap 0 THEN qty = 0 whatever the MoQ.
- **AC-R7 needs_level.** GIVEN no override and master level NULL or 0 THEN `rec_type =
  needs_level`, the suggestion shown, nothing bought.
- **AC-R8 the card order.** The ledger reads Project demand, Retail demand, Net now, The buy,
  History, in that order; project rows carry SO number, customer, delivery date, qty, linked.
- **AC-R9 Set level writes the product row.** Pressing Set level on the plan upserts
  `scm.reorder_level` with `warehouse_id IS NULL`, `source = manual`.
- **AC-R10 disposition unchanged.** BRW's overstock row for SRTWT7408 still appears.

## Phase 2

- **AC-R11 level formula.** GIVEN delivery-order lines (`orders` / `order_lines`) issuing
  900 units of the product over the last 90 days across every warehouse (a cancelled DO's
  100 excluded), lead time 30 THEN ADU = 10, safety stock = 10 x 14 = 140, suggested level =
  10 x 30 + 140 = 440, and the popover names ADU 10 / day, lead 30 d, safety 140. Sales-order
  lines play no part in ADU.
- **AC-R12 health by movement.** GIVEN DO lines in the last 3 months AND a GRN receipt in
  the last 6 months THEN "Fast moving"; DO lines only THEN "Slow moving"; neither with stock
  on hand THEN "Dead - consider discontinuing"; neither and no stock THEN "No history". A
  purchase order issued without a receipt does not count as bought. No margin figure
  anywhere.
- **AC-R13 price switch.** GIVEN a row reading "Ask new price" WHEN the buyer switches it to
  "Use last price" THEN the decision carries `price_mode = use_last`, the row's cost uses the
  last price, and the draft PO line carries it.
- **AC-R14 supplier select.** GIVEN a product with two suppliers WHEN the buyer picks the
  other one THEN the row shows that supplier's last price and lead time, the decision carries
  `supplier_id`, and the draft PO goes to that supplier.
- **AC-R15 no cross-book subtraction.** GIVEN a DO of 50 that names no SO line and a GRN of
  30 matched to no PO line THEN ADU and health count both movements, and net's retail
  outstanding and open PO are exactly the AutoCount outstanding figures, unchanged by either.
