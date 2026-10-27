# UAC - one answer to "where are this SO line's goods now" (LINKAGE-UNIFY)

Plan: `PLAN-linkage-unify-26oct.md`. Status: DRAFT 26 Oct 2026. U1..U4 are ruled; mock v2 approved (09:39), Q6 (a) and no Received card (09:45)
(`documentation/mockups/LINKAGE-UNIFY/index.html`).

## Journey

**Actor:** purchasing / CS on Order Inquiries, planner on Stock Debt.

**Where they arrive from:** OI-2609-0128, SO364824 line 880, SRTSS4210 486 was placed on PO
202607-S0100. AutoCount transferred that PO line onto SPO-2026/09-0107 line 9, and GR-2026/10-0017
received the 486 at BRW-BB on 5 Oct.

**What the system already knows:** the link (on the PO line), the PO line (closed, 486
transferred), the SPO line (486/486 received), the GR line (486 at BRW-BB).

**Steps and the single decision each:**

1. Purchasing opens the OI. The line shows PO 202607-S0100 and SPO-2026/09-0107 with "Received
   486 at BRW-BB"; the state still reads "On PO/SPO". Decision: nothing to chase.
2. Planner opens Stock Debt for SRTSS4210. The line is pinned on on hand at BRW-BB for 486, the
   same place the OI screen named. Decision: nothing to move.
3. Purchasing filters the worklist on "Dead document" and sees the rows whose PO line was
   cancelled or whose SPO line was withdrawn. Decision: re-place each.

**What they hold at the end:** one chain per placement, the same on every screen.

## U1 - the chain (`app/services/scm/goods_chain.py`), behaviour as today

Fixtures: one company, one product, bins B1 and B2, open SO lines. "Placement" = a live
`order_inquiry_links` row (OI row not cancelled, not a reserve link). "Transferred onto" = an
`spo_allocations` row with `from_po_number` = the PO number, `from_po_line_ref` = the PO line's
`source_ref` (any surrounding spaces), same product.

- **AC-C1 On order.** PO line 100 ordered, 0 transferred, open; placement 50. One hop `po`,
  state `on_order`, qty 50.
- **AC-C2 In transit.** PO line 100, 100 transferred onto SPO A 100 allocated, 0 received, open,
  no shipment arrival; placement 50. One hop `spo` A, `in_transit`, 50. No `po` hop.
- **AC-C3 Received.** As AC-C2 but SPO A 100/100 `fully_received`, closed, bin B1. One hop `spo`
  A, `received`, 50, warehouse B1.
- **AC-C4 Partial transfer.** PO line 100, 40 transferred onto SPO A 40 in transit; placement
  100. Hops: `spo` A `in_transit` 40, `po` `on_order` 60.
- **AC-C5 Shared capacity, screen-independent.** PO line 120 transferred onto SPO A 70 (expected
  1 Oct) and SPO B 50 (expected 9 Oct), both in transit. Placement P1 60 (linked first), P2 60.
  P1: A 60. P2: A 10 + B 50. Asking for P2 alone returns the same as asking for both.
- **AC-C6 Key.** An SPO naming the same `from_po_line_ref` under a different PO number, a
  different product, or another company is not followed. A ref with leading/trailing spaces is.
  A retired SPO line with 0 received is not followed (`visible_line_clauses`).
- **AC-C7 Nothing left.** PO line 100 closed, 100 transferred, but only SPO A 50 (in transit)
  names it. Placements P1 50 (linked first) and P2 50. P1: `spo` A `in_transit` 50. P2: no hop,
  `unplaced` 50. (Parity: Stock Debt today pins P1 on A and reads P2's line short.)
- **AC-C8 Stock Debt unchanged.** Every existing test in `tests/scm/` covering SUPPLY-SPO-LINK
  (#1850) and SPO-RECEIVED-PIN (#1388) passes with no edit; `_holds` and `_follow_totals` call
  the chain instead of `_transferred_allocations`.

## U2 - received semantics (rulings Q3, Q4, Q5; Q6 pending)

- **AC-R1 In transit is not received (Q3).** AC-C2 placement: `links_for_rows` entry for the PO
  link has `received` false; `_received_documents_for` does not list it; a replan does not mark
  the row "used"; CS reserve does not count it as received; planning change `received_qty` 0.
- **AC-R2 Landed is received (Q3).** AC-C3 placement: `received` true, `received_qty` 50 (the
  placement's share, not the SPO total).
- **AC-R3 PO received with no SPO, GR known (Q4).** PO line 100 closed, 100 transferred, no SPO
  names it; GR lines naming the PO line: 30 at B1 (1 Sep), 70 at B2 (5 Sep); placement 50. Hops
  `received_direct` 30 at B1 + 20 at B2. Stock Debt pins 30 on on hand B1 and 20 on B2, each
  capped by what the bin holds. OI `received` true.
- **AC-R4 PO received with no SPO, no GR (Q4).** As AC-R3 with no GR line: `received_direct` 50
  at the PO line's own bin.
- **AC-R5 Excel GR.** As AC-R3 but the GR is an Excel GR (no `po_line_id`; header `spo_number`
  holds the PO number, bin in `source_warehouse_id`) and the PO has one line of the product: it
  counts. Two lines of the product on that PO: it does not (fall back to AC-R4).
- **AC-R6 Dead documents (Q5).** PO line cancelled with 0 transferred; Cancel PO (`qty_cancelled`
  = `qty_received`); SPO line retired with 0 received; SPO line closed with nothing landed. Each:
  one hop `dead` with reason `po_cancelled` or `spo_withdrawn`, qty 0; the row state stays
  `placed` ("On PO/SPO", Q2); `received` false; Stock Debt holds nothing.
- **AC-R7 GR bin for SPO receipts (Q6 (a), ruled).** SPO A received 260, SPO bin B1, GR
  line naming A received 260 at B2: hop `received` at B2; Stock Debt pins on B2. Real case:
  OI-2609-0352, SO396194 L1216, CGB762 260, SPO-2026/08-0083 L29 (bin BRW-BB, 0 on hand),
  GR-2026/08-0155 at MWH.
- **AC-R8 One key.** `po_lines_with_open_chained_spo` (PS:13453) and the own-arrival readers
  (PSS:3107, 3184, 3312) answer through the chain's key: a space-padded `from_po_line_ref` gives
  the same answer in all of them.

## U3 / U4 - display (after the owner approves the mock)

- **AC-D1 (Q1).** OI Lines tab and worklist: a PO-placed line whose SPO is received shows the PO
  chip and the SPO chip; the SPO chip carries "Received <qty> at <bin>" (L880: "Received 486 at
  BRW-BB"). The PO chip never carries a "received" pill (owner note on mock v1); the received
  state shows only on the SPO chip. Class d (no SPO): the PO chip carries "Received <qty> at <bin>" from its GR (lead default, the
  mock v2 ask; owner may override).
- **AC-D2 (Q2).** The state pill reads "On PO/SPO" on every placed row, unchanged.
- **AC-D3 (Q5).** Dead hops show red "PO cancelled" / "SPO withdrawn"; the worklist "Dead
  document" filter lists exactly those rows; a retired SPO link is no longer hidden.
- **AC-D4 (parity).** The Lines tab draws the same document pills as the worklist.
- **AC-D5 (owner 09:45).** Worklist stage cards are unchanged: no Received card; landed units
  stay in Purchased as today.
- **AC-D6 (U4).** PO popup SPO column shows each SPO with its state; "Allocated to" on the PO
  popup, the SPO popup and the SPO document lists every placement whose chain passes through
  that document (OI-2609-0128 L880 appears on SPO-2026/09-0107's).
- Every changed screen usable at 375 and 1280 px; no UUIDs; no explanatory text in the UI.

## Test list (tester writes these red, from this file only)

- `tests/scm/test_goods_chain.py` (new): AC-C1..C7, AC-R3..R7 at the chain level.
- `tests/scm/test_stock_debt_routes.py` and the existing SUPPLY-SPO-LINK / SPO-RECEIVED-PIN
  tests: AC-C8 unchanged; AC-R3, AC-R4, AC-R6, AC-R7 through the Stock Debt cell.
- OI received tests (find the existing #973 / #1708 suites): AC-R1, AC-R2, AC-R6, AC-R8.
- FE vitest for the pills and filter (U3): AC-D1..D4.
- Postgres only (`tests/_pg_fixture.py`), seed the whole chain (CI DB has no data).
