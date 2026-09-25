# UAC: Order inquiry view without double counting

Status: DRAFT, pending the owner's grill (G1-G10 in the plan). Every AC below assumes the
recommended answer; an AC whose grill question is ruled differently is rewritten before Phase 1.
Plan: `PLAN-oi-no-double-count-25sep.md`
Issue: #1248

## Journey

1. The reader opens an order inquiry from the Order Inquiries list or from the sales order's
   "Order inquiry" cell.
2. The Lines tab reads like the sales order's Lines grid: one row per sales order line, in the
   sales order's line order, the same product and Qty, then Buy, the documents and the State.
3. A line that changed after its PO was received still shows one row, with its current need and
   "Was / now" in State.
4. Purchasing ticks lines and presses Confirm (N); used rows behind a line are acknowledged with
   it.
5. The History icon in a line's State cell opens one dialog for that line: Rows (every retired
   row), Decisions (#1244 trail), Reserve (when the line has reserve history).
6. The header list's Lines and Qty foot to what the detail shows.

## Phase 1 - frontend, mocked (S0)

- AC-ND-1 [FE] (journey 2, G5) Given an inquiry whose rows cover sales order lines L1..Ln, when
  the Lines tab renders, then it shows exactly one grid row per distinct `so_line_id`, plus one
  row per row whose `so_line_id` is null, and no other rows.
- AC-ND-2 [FE] (journey 2) Rows sort by sales order line No. ascending; null-line rows sort last.
- AC-ND-3 [FE] (journey 2, G4) Columns, in order: Select, No., Product, Qty, Buy, Delivery date,
  Location, Supplier, PO, SPO, Suggested, Instruction, State. The "SO line" column is gone from
  the detail. "Raised via" stays hidden by default.
- AC-ND-4 [FE] (G4) Qty shows the sales order line's own Qty (`so_line_qty`), the number the
  sales order's Lines grid shows for that line.
- AC-ND-5 [FE] (G5) Buy = sum of `qty` over the line's live buy rows (verb ORDER / ORDER_BACK,
  `state` in raised / partly_linked / placed / actioned, `redirected_to_pool` false). A
  CANCEL_BALANCE, DELAY, ADVANCE or CHANGE_SO row never adds to Buy.
- AC-ND-6 [FE] (G4) When Buy < Qty, the Buy cell's `title` reads "<Qty - Buy> from stock".
- AC-ND-7 [FE] (journey 3, G1) Given a line with a used row of 2 (PO-2026/09-0023 received) and
  a fresh row of 5 whose note starts "Replaces 2 used", then the line renders ONE row: Qty 5,
  Buy 5, State "To confirm" with "Was 2, now 5". No "used" pill appears on the main grid.
- AC-ND-8 [FE] (G5) Given a line with a partly linked row of 6 on PO-0031 and a fresh raised row
  of 4, then ONE row: Buy 10, PO cell "PO-0031", State "Partly on PO".
- AC-ND-9 [FE] (G5) Given a 728 line split into two 364 rows on two SPOs, then ONE row: Buy 728,
  SPO cell names the first SPO plus "+1"; clicking "+1" lists both.
- AC-ND-10 [FE] (G7) A cancelled sales order line (`line_cancelled`) renders ONE grey row, Buy 0,
  State "Line cancelled", before and after Confirm.
- AC-ND-11 [FE] (O2) A line with no live row and not cancelled renders ONE grey row, Buy 0, State
  "Nothing to buy", with its History icon.
- AC-ND-12 [FE] (journey 4) Ticking a line selects all of its live rows; Confirm (N) counts lines,
  not rows; a line with no live row cannot be ticked.
- AC-ND-13 [FE] (journey 5, G3) Every line row's State cell carries exactly ONE History icon
  button (aria-label "History"); no reserve History icon and no second decision-trail icon remain.
- AC-ND-14 [FE] (G2, G3) The History dialog is titled "History - <item> (<SO> L<n>)" and has line
  tabs Rows | Decisions, plus Reserve only when the line has reserve history. Rows is the default
  tab.
- AC-ND-15 [FE] (journey 5) The Rows tab is a `DataGrid` (fixed layout, resizable, explicit
  sizes, truncate + title) with columns When, Qty, What, Document, Why. The live row is first,
  tagged "Now"; retired rows follow newest first. What is a `Badge` pill: Used / Superseded /
  Re-raised / Cancelled / Cancel balance / Line cancelled.
- AC-ND-16 [FE] (journey 5) Rows tab with no retired rows reads "No earlier rows for this line."
- AC-ND-17 [FE] (header totals) The Lines tab footer Qty foots Qty and Buy over the visible line
  rows; the header card's Qty equals the Buy total.

## Phase 2 - backend (S1), wiring (S2), worklist (S3)

- AC-ND-20 [BE][T] `GET /order-inquiries?inquiry_id=X&include_history=true` returns every row of
  the header, cancelled included; without the flag the response is unchanged.
- AC-ND-21 [BE][T] Every worklist row carries `so_line_qty` and `so_line_no`, declared on
  `OrderInquiryWorklistRow` and asserted by name through the route; both null when `so_line_id` is
  null.
- AC-ND-22 [BE][T] (G10) Header list: given a header with a used row of 182 and a fresh row of 220
  on the same sales order line, `lines_total` = 1 and `qty_total` = 220.
- AC-ND-23 [BE][T] (G10) Two null-line rows count as two lines.
- AC-ND-24 [BE][T] (G6) Confirming a line's live rows also moves that line's
  `redirected_to_pool` rows on the same header from `changed` to `acknowledged`, in the same
  call; `lines_to_confirm` for the header drops to 0 when nothing else waits.
- AC-ND-25 [BE][T] (G6) Confirming does not touch a used row on another sales order line or on
  another header.
- AC-ND-26 [BE][T] (out of scope guard) No write path changes: a replan of the #1248 case still
  produces a used row of 2 and a fresh ORDER row whose note starts "Replaces 2 used" (existing
  tests stay green unchanged).
- AC-ND-27 [FE] (S2) Link selected (#1220) sends the live row ids of the ticked lines, never a
  used or cancelled row id.
- AC-ND-28 [FE][BE] (G8, S3) The worklist hides used rows and confirmed cancelled-line rows by
  default; the State filter's "History" choice brings them back, greyed as today.

## Phase 3

- AC-ND-30 [E2E] agent-browser, sidebar navigation from `/` to Order Inquiries, open an inquiry
  holding the #1248 shape: one row per sales order line, Qty column equal to the sales order's
  Lines grid for the same lines (read on the SO detail in the same run), History dialog opens and
  lists the used row. Evidence at 1280 and 375.
- AC-ND-31 [UX] At 375 the grid scrolls sideways inside its own scroller, no page scroll; the
  History dialog fits the viewport with its tab strip scrolling, never wrapping.
- AC-ND-32 [UX] No-motion list: the fold, the line row, the History icon and the tab switch do
  not animate; only the dialog uses the standard lightbox surface spring, reduced motion honoured.
