# UAC - a received SPO must not keep covering an SO on Stock Debt (SPO-RECEIVED-PIN)

Plan: `PLAN-spo-received-pin.md`. Status: in progress, 30 Sep 2026.

## Journey

**Actor:** CS planner on Supply Chain > Stock Debt, opening the drawer for one product.

**Where they arrive from:** SRTSS8710 had an order inquiry placement on SPO-2026/05-0001. The
SPO line has since been fully received into the bin. The stock balance upload shows the goods
on hand.

**What the system already knows:** the SPO line is fully received, so it is out of incoming
supply. The placement link is still on the OI row.

**Steps and the single decision each:**

1. Planner opens the product's cell for the SO's month. Today the SO line reads Pinned,
   Covered by SPO-2026/05-0001, and the bin's on hand also covers another line: more coverage
   than stock. Under this plan the line reads Pinned, Covered by On hand <bin>, and the other
   line reads what the remaining free stock allows.
2. Planner opens the Supply tab for the same month. No SPO-2026/05-0001 row, because it is not
   incoming; the on-hand row names the pinned SO in Assigned to.

**What they hold at the end:** one figure for the landed goods, on the line that bought them.

## Acceptance criteria

- **AC-1 Fully received placement.** Bin holds 50. SO1 50 has a placement of 50 on an SPO line
  fully received (`quantity_received = allocated`, `receipt_status = fully_received`) at that
  bin. SO2 50 at the same bin, same month, no placement. Cell: SO1 `pinned`, `assigned_qty 50`,
  `assigned_from` one entry `kind on_hand` naming the bin; SO2 `short`, `uncovered 50`. Supply
  tab: no `kind spo` row; `supply_total_qty 50`; the on-hand row's `assigned_to` names SO1 for 50.
- **AC-2 Landed shipment.** Same as AC-1 but the SPO line has `quantity_received 0` and an
  inbound shipment with `actual_arrival_date` set. Same outcome as AC-1.
- **AC-3 Goods gone.** Fully received SPO placement of 50, bin holds 0. SO1 `short`,
  `uncovered 50`, `assigned_from` empty. No stand-in SPO row anywhere in the cell.
- **AC-4 Partial receipt still pins the SPO.** SPO 100, received 30, `receipt_status pending`,
  placement 50. SO1 `pinned`, `assigned_from` one entry `kind spo` for 50. The SPO row shows
  `qty 100`, `received_qty 30`, `outstanding_qty 70`.
- **AC-5 Both readers.** The conversion happens in `_holds`, so the board path
  (`assignments_for`) reads the same hold. Covered by the route tests through the shared code,
  no separate board test.
