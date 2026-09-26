# UAC: Order inquiry view without double counting

Status: grilled. Owner rulings 26 Sep 2026 are folded in as dated "Owner ruling 26 Sep" lines
under each AC they change; where a ruling line and the AC text disagree, the ruling line governs.
No AC is deleted; AC-ND-28 is dropped by ruling G8 and kept as a record.
Plan: `PLAN-oi-no-double-count-25sep.md`
Issue: #1248

## Journey

1. The reader opens an order inquiry from the Order Inquiries list or from the sales order's
   "Order inquiry" cell.
2. The Lines tab reads like the sales order's Lines grid: one row per sales order line, in the
   sales order's line order, the same product and Qty, then Buy, the documents and the State.
   Owner ruling 26 Sep (G4): SO Qty, Requested, Taken, Remaining replace Qty / Buy.
3. A line that changed after its PO was received still shows one row, with its current need and
   "Was / now" in State.
   Owner ruling 26 Sep (G1): no "Was / now" on the main view; it reads in History only.
4. Purchasing ticks lines and presses Confirm (N); used rows behind a line are acknowledged with
   it.
5. The History icon in a line's State cell opens one dialog for that line: Rows (every retired
   row), Decisions (#1244 trail), Reserve (when the line has reserve history).
6. The header list's Lines and Qty foot to what the detail shows.
   Owner ruling 26 Sep (G10): exactly what the Lines tab shows (Lines = rendered line rows,
   Qty = the Requested footer).

## Phase 1 - frontend, mocked (S0)

- AC-ND-1 [FE] (journey 2, G5) Given an inquiry whose rows cover sales order lines L1..Ln, when
  the Lines tab renders, then it shows exactly one grid row per distinct `so_line_id`, plus one
  row per row whose `so_line_id` is null, and no other rows.
  Owner ruling 26 Sep (G5): always one row per sales order line, whatever the split. S0 folds by
  `core_line_id` (the payload's resolved form of `so_line_id`), else `so_number` + `line_no`,
  else the row alone.
  Fix round 2 (PR #1266 review S1, 26 Sep): the rows carry `so_line_id` (the mirror line) and
  the fold keys on it, the same key the header's `lines_total` reads. A line not yet
  reconciled to AutoCount (`core_sales_order_line_id` null) is still ONE line, and its SO Qty
  counts once in the footer.
- AC-ND-2 [FE] (journey 2) Rows sort by sales order line No. ascending; null-line rows sort last.
- AC-ND-3 [FE] (journey 2, G4) Columns, in order: Select, No., Product, Qty, Buy, Delivery date,
  Location, Supplier, PO, SPO, Suggested, Instruction, State. The "SO line" column is gone from
  the detail. "Raised via" stays hidden by default.
  Owner ruling 26 Sep (G4): columns in order: Expand, Select, No., Product, SO Qty, Requested,
  Taken, Remaining, Delivery date, Supplier, PO, SPO, Suggested, Location, Instruction, State.
  Owner ruling 26 Sep (W1): a narrow Confirmed mark column sits between Product and SO Qty
  (AC-ND-33).
- AC-ND-4 [FE] (G4) Qty shows the sales order line's own Qty (`so_line_qty`), the number the
  sales order's Lines grid shows for that line.
  Owner ruling 26 Sep (G4): the column is titled "SO Qty". S0 mocks it (`so_line_qty` when
  present, else the line's Requested), marked as mocked in code; S2 wires the real field.
- AC-ND-5 [FE] (G5) Buy = sum of `qty` over the line's live buy rows (verb ORDER / ORDER_BACK,
  `state` in raised / partly_linked / placed / actioned, `redirected_to_pool` false). A
  CANCEL_BALANCE, DELAY, ADVANCE or CHANGE_SO row never adds to Buy.
  Owner ruling 26 Sep (G4): the column is titled "Requested" (what CS raised to buy) and the
  buy verbs are the existing `isInquiryBuyRow` set (ORDER, ORDER_BACK, RESERVE_AND_ORDER).
  AC-ND-5a Taken = sum of `linked_qty + reserved_qty` over the same rows. AC-ND-5b Remaining =
  Requested - Taken - `bundled_qty` summed over the same rows, never negative; 0 on a cancelled
  line.
- AC-ND-6 [FE] (G4) When Buy < Qty, the Buy cell's `title` reads "<Qty - Buy> from stock".
  Owner ruling 26 Sep (G4): withdrawn; no "from stock" hover. Requested, Taken and Remaining
  carry no title beyond the number.
- AC-ND-7 [FE] (journey 3, G1) Given a line with a used row of 2 (PO-2026/09-0023 received) and
  a fresh row of 5 whose note starts "Replaces 2 used", then the line renders ONE row: Qty 5,
  Buy 5, State "To confirm" with "Was 2, now 5". No "used" pill appears on the main grid.
  Owner ruling 26 Sep (G1): ONE row, Requested 5, State "To confirm"; no "Was 2, now 5" text, no
  Qty (i) Was button and no "used" pill anywhere on the main grid. The used row of 2 is listed in
  History's Rows tab as "Used".
  "To confirm" is the line State whenever a live buy row's `ack_state` is `changed`; a fresh row
  born `awaiting` still reads its own state (AC-ND-8 reads To buy). Fix round 2 (review S2): a
  line with a WAITING used row (not cancelled, ack `awaiting` or `changed`) reads "To confirm"
  too, whether its live rows are already confirmed or it has none (then it is not greyed
  until the used row is confirmed); a cancelled SO line still reads "Line cancelled". The
  Instruction cell shows the
  pill only; the row's note ("Replaces 2 used ...") reads in History's Why, never on the grid.
- AC-ND-8 [FE] (G5) Given a line with a partly linked row of 6 on PO-0031 and a fresh raised row
  of 4, then ONE row: Buy 10, PO cell "PO-0031", State "Partly on PO".
  Owner ruling 26 Sep (G4, G5): ONE row, Requested 10, Taken 6, Remaining 4, PO cell "PO-0031";
  State is the most urgent live state, To buy (raised beats partly linked).
- AC-ND-9 [FE] (G5) Given a 728 line split into two 364 rows on two SPOs, then ONE row: Buy 728,
  SPO cell names the first SPO plus "+1"; clicking "+1" lists both.
  Owner ruling 26 Sep (G5): Requested 728, Taken 728, Remaining 0; the two rows are listed in
  History as Now.
- AC-ND-9a [FE] (Owner ruling 26 Sep, G5) DELAY / ADVANCE / CANCEL_BALANCE rows on a line fold
  into its one row, add to no quantity, and the most urgent of them (CANCEL_BALANCE > CHANGE_SO >
  DELAY > ADVANCE) is the line's Instruction.
- AC-ND-10 [FE] (G7) A cancelled sales order line (`line_cancelled`) renders ONE grey row, Buy 0,
  State "Line cancelled", before and after Confirm.
  Owner ruling 26 Sep (G7): the grey row stays on the main view; Requested 0, Remaining 0; its
  used rows are in History, never on the main grid.
- AC-ND-11 [FE] (O2) A line with no live row and not cancelled renders ONE grey row, Buy 0, State
  "Nothing to buy", with its History icon.
  Owner ruling 26 Sep (O2): accepted; Requested, Taken and Remaining all 0.
- AC-ND-12 [FE] (journey 4) Ticking a line selects all of its live rows; Confirm (N) counts lines,
  not rows; a line with no live row cannot be ticked.
  Owner ruling 26 Sep (G6): Confirm also sends the ticked lines' used rows whose ack is
  `changed`.
  Fix round 2 (review S2): a line whose only waiting rows are used ones can be ticked (a line
  with no live row ticks its waiting used rows), and Confirm sends those used row ids; a line
  with a live row still waiting sends its live rows and the server sweeps the used ones. Link,
  Unlink, Reject and Unconfirm read live rows only, and a tick on a used-only line never
  widens Unconfirm or Auto link to the whole OI.
- AC-ND-13 [FE] (journey 5, G3) Every line row's State cell carries exactly ONE History icon
  button (aria-label "History"); no reserve History icon and no second decision-trail icon remain.
  Owner ruling 26 Sep (G3): accepted as written.
- AC-ND-14 [FE] (G2, G3) The History dialog is titled "History - <item> (<SO> L<n>)" and has line
  tabs Rows | Decisions, plus Reserve only when the line has reserve history. Rows is the default
  tab.
  Owner ruling 26 Sep (G2, G3): accepted as written; rows on amendment headers are not listed
  (O1).
- AC-ND-15 [FE] (journey 5) The Rows tab is a `DataGrid` (fixed layout, resizable, explicit
  sizes, truncate + title) with columns When, Qty, What, Document, Why. The live row is first,
  tagged "Now"; retired rows follow newest first. What is a `Badge` pill: Used / Superseded /
  Re-raised / Cancelled / Cancel balance / Line cancelled.
  Owner ruling 26 Sep (G1, G6): every row that is not the line's current need is listed here,
  the used row included; the Now row's Why reads "Was <previous_qty>" before its note when it
  has one (the only place the Was / now story shows). Re-raised is a "Superseded by revision N"
  row that a later row of the same line asks for again at the same qty; any other superseded row
  reads Superseded.
- AC-ND-16 [FE] (journey 5) Rows tab with no retired rows reads "No earlier rows for this line."
  While the cancelled rows load it shows a skeleton, and if the read fails it shows the error,
  never the empty text.
- AC-ND-17 [FE] (header totals) The Lines tab footer Qty foots Qty and Buy over the visible line
  rows; the header card's Qty equals the Buy total.
  Owner ruling 26 Sep (G4, G10): the footer totals SO Qty, Requested, Taken and Remaining over
  the line rows, cancelled lines excluded; the header list's Qty equals the Requested total and
  its Lines equals the number of line rows rendered.
- AC-ND-18 [UX] (Owner ruling 26 Sep, brief) Every grid on the screen (the Lines grid and the
  History Rows grid) scrolls sideways inside its own container at 375; the page never scrolls
  sideways. The DataGrid scroller census lists the History Rows grid; the nesting census does not
  change, since the dialog is a sibling of the Lines grid, not inside it.

## Phase 2 - backend (S1), wiring (S2); worklist (S3) dropped by owner ruling 26 Sep (G8)

- AC-ND-20 [BE][T] `GET /order-inquiries?inquiry_id=X&include_history=true` returns every row of
  the header, cancelled included; without the flag the response is unchanged.
- AC-ND-21 [BE][T] Every worklist row carries `so_line_qty` and `so_line_no`, declared on
  `OrderInquiryWorklistRow` and asserted by name through the route; both null when `so_line_id` is
  null.
- AC-ND-22 [BE][T] (G10) Header list: given a header with a used row of 182 and a fresh row of 220
  on the same sales order line, `lines_total` = 1 and `qty_total` = 220.
  Owner ruling 26 Sep (G10): and a cancelled sales order line counts in `lines_total` (it is a
  rendered grey row) but adds 0 to `qty_total`.
- AC-ND-23 [BE][T] (G10) Two null-line rows count as two lines.
- AC-ND-24 [BE][T] (G6) Confirming a line's live rows also moves that line's
  `redirected_to_pool` rows on the same header from `changed` to `acknowledged`, in the same
  call; `lines_to_confirm` for the header drops to 0 when nothing else waits.
  Fix round 2 (review S2): ONE rule for a waiting used row - not cancelled, ack `awaiting` or
  `changed` - read by `lines_to_confirm`, the line State and the sweep alike, so a used row
  redirected before anyone read it (`awaiting`) is swept too. The (header, line) pair is
  matched in SQL (review N1).
- AC-ND-25 [BE][T] (G6) Confirming does not touch a used row on another sales order line or on
  another header.
- AC-ND-26 [BE][T] (out of scope guard) No write path changes: a replan of the #1248 case still
  produces a used row of 2 and a fresh ORDER row whose note starts "Replaces 2 used" (existing
  tests stay green unchanged).
- AC-ND-27 [FE] (S2) Link selected (#1220) sends the live row ids of the ticked lines, never a
  used or cancelled row id.
- AC-ND-28 [FE][BE] (G8, S3) The worklist hides used rows and confirmed cancelled-line rows by
  default; the State filter's "History" choice brings them back, greyed as today.
  Owner ruling 26 Sep (G8): DROPPED. The worklist is being discontinued; no worklist change.
  Kept here as the record.

## Fix round W1 (owner hand test of S1 + S2, 26 Sep ~11:20Z)

Owner, verbatim: "i just realized after we click confirm, at the line level can't really see it
is confirmed, can we have an icon here to show it is confirmed?" (the gap between Product and SO
Qty boxed).

- AC-ND-33 [FE] A narrow, unsortable column between Product and SO Qty (header blank, named
  "Confirmed" for screen readers and the Columns picker) carries the line's confirmation, read
  over the same fold as the rest of the line (its live rows; cancelled and used rows ignored; a
  rejected row is left out of the count):
  - every counted row `acknowledged`: the worklist PO cell's confirmed mark (`CircleCheck`,
    emerald), tooltip "Confirmed by <name> on <date>", the latest confirmer;
  - some but not all: the worklist's pending mark (`CircleDashed`, muted), tooltip "n of m rows
    confirmed";
  - none confirmed yet: nothing (the State cell already says what waits);
  - a cancelled SO line is marked like any other line (review SF1): its rows go back to
    `changed` and wait on Confirm (G7), and its State reads "Line cancelled" before and after,
    so the mark is the only place Confirm shows on it.
  Two choices named here for the owner (review N1, N2): a rejected row is left out of n of m, so
  1 confirmed + 1 rejected reads the check; a used (`redirected_to_pool`) row is not counted,
  the same fold rule as the rest of the line, even though the header's `lines_to_confirm`
  counts a used row still in `changed` (Confirm sweeps it with its line, G6).
  It updates in place after Confirm, with no reload (the Confirm mutation refetches the Lines).
  Evidence: `evidence/oi-no-double-count-w1/`.

## Phase 3

- AC-ND-30 [E2E] agent-browser, sidebar navigation from `/` to Order Inquiries, open an inquiry
  holding the #1248 shape: one row per sales order line, Qty column equal to the sales order's
  Lines grid for the same lines (read on the SO detail in the same run), History dialog opens and
  lists the used row. Evidence at 1280 and 375.
  Owner ruling 26 Sep (G4): SO Qty is the column compared with the sales order's Lines grid.
- AC-ND-31 [UX] At 375 the grid scrolls sideways inside its own scroller, no page scroll; the
  History dialog fits the viewport with its tab strip scrolling, never wrapping.
- AC-ND-32 [UX] No-motion list: the fold, the line row, the History icon and the tab switch do
  not animate; only the dialog uses the standard lightbox surface spring, reduced motion honoured.
