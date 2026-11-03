# UAC: One delivery date, OI rows use the SO line delivery date

Plan: `PLAN-oi-one-delivery-date-03nov.md`. Card: `OI-ONE-DELIVERY-DATE-card.md` (owner answers
3 Nov 22:50: Q1 a, Q2 a, Q3 a, Q4 print 2030 as it is, Q5 a, plus "show OI date changes the same way
as SO line changes").

Terms. **SO line date**: the core `sales_order_lines.required_date` of the OI row's SO line
(`order_inquiry_rows.so_line_id -> projects.sales_order_lines.core_sales_order_line_id`); the mirror
line's `delivery_date` when no core line is linked; the row's own stored date only when the row has
no SO line or the line has no date at all. **Told date**: the stored `order_inquiry_rows.delivery_date`
(the date purchasing was last told). **Was**: the told date when it differs from the SO line date,
else `previous_delivery_date` when that differs from the SO line date, else none.

## A. One date everywhere

- AC-A1: The OI worklist, the OI detail Lines tab and the per-project OI list print the SO line date
  in "Delivery date". OI-2609-0588 / SO397450 L312 B2155-NL-BLUE reads 07/01/2027, not 01/07/2026.
- AC-A2: Sorting by Delivery date sorts the whole result on the server by the SO line date.
- AC-A3: The month tabs, the schedule matrix and its drilldown, and the delivery from / to filters
  bucket and filter by the SO line date (a row whose line is 07/01/2027 sits under January 2027).
- AC-A4: The "Request CS to reserve" dialog, the reserve request email and the reserved notice print
  the SO line date and sort by it; the 31 Oct reserve rules are unchanged (full table, one email per
  raised_by CS, the button opens exactly that email's OIs, no TOTAL QTY, rejected line says
  "Rejected").
- AC-A5: The OI handover email, its send / resend preview and its Excel attachment print the same
  SO line date for every line (email = preview = attachment). A line whose SO date moved prints the
  old date as DELIVERY DATE and the SO line date as DELIVERY DATE CHANGE TO, as today.
- AC-A6: The undo email and the Confirm preview's inquiry rows print the SO line date.
- AC-A7: A Stock Debt snapshot taken after the release freezes the SO line date on its OI rows; the
  live Stock Debt view is unchanged (it already reads the SO line).
- AC-A8: Link suggestions ("arrives in time" window, candidate order, "needed <date>"), the ETA
  fallback, and the plan / reorder project demand legs (horizon, need dates, month buckets, SPO "SO
  covered" picker) use the SO line date.
- AC-A9: The worklist and per-project Excel / PDF exports print the SO line date (they read the
  same fields; OI-EXPORT-SHARED's sort follows it).
- AC-A10: An SO line on 2030-01-01 prints 01/01/2030 everywhere (Q4: no TBA label).
- AC-A11: A row whose SO line has no date prints its told date; a row with no SO line prints its
  told date.
- AC-A12: Where the mirror line lags its core line (SO314593 L6: mirror 2026-06-01, core 2030-01-01),
  the core date wins.

## B. Pending AutoCount change (Q1 a)

- AC-B1: AutoCount moves an SO line's date and CS has not confirmed the planning change: the OI shows
  the new SO line date at once, with Was = the told date.
- AC-B2: When CS confirms, the OI email says DELAY / ADVANCE exactly as today (the told date is the
  "was"); afterwards the OI still shows the SO line date, Was = `previous_delivery_date`.
- AC-B3: No OI email is sent by an AutoCount push on its own.

## C. Sheet import and backfill (Q2 a, Q5 a)

- AC-C1: The OI sheet upload writes the SO line date on a new row; when the sheet's date differs, the
  sheet's date is kept as the Was (`previous_delivery_date`). The sheet's date still decides which
  line a row matches.
- AC-C2: The upload no longer reports or performs "Dates corrected" (the tile goes).
- AC-C3: A data migration sets, on every row not cancelled whose SO line date differs from its told
  date: `previous_delivery_date` = the told date, told date = the SO line date. Rows that already
  match, rows with no SO line and rows whose line has no date are untouched. On the 20 Oct copy that
  is 2,685 rows.
- AC-C4: The migration sends no email and writes no planning change, ack change or audit row of its
  own; it records each changed row (id, old told date, old previous date) in its own table so the
  downgrade restores them exactly.
- AC-C5: Several rows on one SO line at different dates (SO369829 L27 M228-CR: 01/02, 01/03,
  01/04/2027, line 30/12/2027) each print 30/12/2027, Was their own old date.

## D. Split SO lines (Q3 a)

- AC-D1: A split line's rows in the email, preview and Excel keep today's shape: DELIVERY DATE is
  the line's base date (the date before the split moved it, the "was" of its DELAY / ADVANCE), each
  part's own date is CHANGE DATE (same rule as AC-A5 for any changed line).
- AC-D2: In the OI Lines tab split grid, a part that sits on an SO line prints that line's SO line
  date, followed by a muted "planned <date>" when its own planned date differs; a part with no line
  yet in AutoCount prints its own date followed by "planned". A cancel part prints as today.

## E. How a change shows (owner extra)

- AC-E1: A Delivery date cell whose row has a Was shows the same amber "What changed" icon the SO
  line uses (`BoardChangeTable`), next to the date.
- AC-E2: The icon opens the same lightbox, titled "What changed, <SO> (Line <n>)", with the Was / Now
  table: Date row Was = the Was date, Now = the SO line date.
- AC-E3: A row with no Was shows no icon. The "Changed" pill on `ack_state = changed` stays.
- AC-E4: The Qty (i) dialog's Was / Now Date row uses the same Was and Now as AC-E2.
- AC-E5: Usable at 375px and 1280px.
