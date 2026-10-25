# PLAN: Supply tab double counts a transferred PO line; show the SPO a PO line moved onto

Status: Build (small fix track, S: backend fix in one service + one Supply column; no migration, no RBAC).
Lane: SUPPLY-SPO-LINK, branch `crew/supply-spo-link`. Owner prod report 25 Oct 2026.

## 1. The report

Product popup (Stock Debt cell, `StockDebtCellDialog.tsx`) for one product lists the same PO
twice as supply (490 and 486, Received blank, Bin `-`, no line number), each assigned to an SO
line, while the PO popup shows those lines Ordered = Received, Remaining 0, and the SPO they moved
onto is Completed. The same goods sit in On hand at the bin, which the popup assigns to two OTHER
lines of the same orders. Supply foots 2,952 where 1,976 is real.

Owner ruling (standing): once a PO line is received it is on-hand quantity and is not supply.
A partly received line counts only what is still on order.

## 2. Root cause (file:line on origin/main 47881ef118)

1. `ProjectSupplyService._po_rows` (`app/services/project_supply_service.py:10147-10159`) reads a
   PO line as supply only while `line_status = 'open'` and `qty_ordered > qty_received`. A fully
   received line is (correctly) not in the span's events.
2. `StockDebtService._holds` (`app/services/scm/stock_debt_service.py:1800-1820`) turns every live
   `order_inquiry_links` row on a PO line into a `po:<line>` hold with the link's full qty. It never
   asks whether the line is still on order. The SPO branch right below it has that check
   (SPO-RECEIVED-PIN, `:1821-1856`); the PO branch has none.
3. `assign()` (`app/services/scm/supply_assignment.py:758-780`, AC-S2-1b) honours a hold whose
   supply is not in the span by standing an event up FROM THE HOLD: kind PO, no bin, no received,
   no line number, `at = as_of`, qty = the whole link. That event is appended to `counted`, so it is
   counted in the month as supply. This is the `PO 202607-S0100` row with Bin `-` and blank
   Received.
4. The goods themselves are already On hand (the SPO they moved onto landed), and nothing pins them
   to the lines the placement was for (those lines read covered by the phantom PO), so the walk
   hands the on-hand units to the next open lines of the same product. Hence "assigned to both".

Data fact that shapes the fix (code doctrine at `project_supply_service.py:3118-3123`, R7
follow-up, and measured on the dev DB `sorento_cagent_stack` 25 Oct): `purchase_order_lines
.qty_received` is the AutoCount TRANSFER onto a shipping order, not a physical receipt. 71,371 of
72,067 PO lines with a derived SPO have `qty_received = sum(spo allocated)`; 729 read fully
received while their SPO is still in transit. What landed is `spo_allocations.quantity_received`.
So a PO line that dropped out of supply has its goods either on an incoming SPO (already supply)
or on hand (already supply). Either way the placement must follow the goods, never stand the PO
back up.

Dev reproduction: the same product, same PO, same two auto placements exist on the dev DB
(PO lines 490/490 and 486/486 closed, SPO lines fully received, bin stock 976).
Population on dev: 334 live placements on open SO lines name a PO line that is no longer on
order; 303 of them have a derived SPO (114 still in transit).

## 3. The fix (one rule, two existing mechanisms reused)

A placement on a PO line holds:

- the PO line only for what it still has ON ORDER: `min(link qty, qty_ordered - qty_received)`
  while the line passes the same open-PO predicate `_po_rows` uses (shared, not restated:
  `ProjectSupplyService.open_po_line_clauses()`), else 0;
- the rest on the SPO allocations the line was transferred onto, found with the OI page's own key
  OI-SPO-EXACT (`from_po_number = po_number AND trim(from_po_line_ref) = trim(po_line.source_ref)
  AND product_id = po_line.product_id`, live allocations only, company predicate stated by hand as
  in `project_order_inquiry_service._append_derived_spo_entries`), each through the SPO branch's
  own rule: still incoming -> an SPO hold; landed -> an on-hand hold at the SPO's bin for what it
  landed (SPO-RECEIVED-PIN), dropped when the bin is in span and empty;
- nothing for whatever is neither (a short-closed line), which is what the ruling asks.

`_holds` is the only builder of these holds; `_assignments` feeds it to the Stock Debt list
(`list`), the drill (`cell`), and `assignments_for` -> `ProjectSupplyService.planning_assignments`
(fulfilment board, confirm recheck, order inquiry picker). One fix covers every consumer.
The order inquiry PO candidates (`project_order_inquiry_service.py:10382-10388`) already net
`qty_ordered - qty_received` and never offered a transferred line: no change.

## 4. UI: the SPO a PO line moved onto

Supply grid of `StockDebtCellDialog` (the only consumer of this grid; `/project-sales/stock-debt`)
gains an `SPO` column after Document: for a PO row, every SPO number its line was transferred onto
(OI-SPO-EXACT, live allocations), each an `OrderInquiryDocumentLink kind="spo"` (the link the
Document cell already uses for an SPO row); `-` otherwise. Backend: `spo_numbers: string[]` on each
supply row (`app/schemas/stock_debt.py` supply event), one batched read per drill.
Mockup first: `documentation/mockups/SUPPLY-SPO-LINK/index.html` (crew contract).

## 5. Tests (red first, `tests/scm/`)

- R1 fully transferred + landed: PO-line placement, SPO fully received at bin B with stock; drill
  lists no PO row, the line is pinned on `On hand B`, supply total = on hand only.
- R2 fully transferred, SPO in transit: the line is pinned on the SPO row; no PO row.
- R3 partly transferred, open: PO row Outstanding = ordered - received, the line pinned on the PO
  for at most that, the rest on the derived SPO.
- R4 short-closed, nothing transferred: placement pins nothing, no PO row.
- R5 the supply row of a PO line carries `spo_numbers` (derived allocations), `[]` for on hand.
- FE: the SPO column renders a link per number and `-` when empty.

## 6. Out of scope

- A partly received SPO's landed part stays as today (SPO hold capped by outstanding).
- #1667 (STOCK-DEBT-DECOUPLE) edits `project_supply_service.py:70-160, 248-800`; this lane adds a
  static helper beside `_po_rows` (~10066) only. No textual overlap.
