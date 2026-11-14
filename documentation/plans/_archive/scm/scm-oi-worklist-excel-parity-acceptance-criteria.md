# Acceptance criteria: order inquiries worklist, Excel parity batch (16 Sep 2026)

Companion to `PLAN-scm-oi-worklist-excel-parity.md`. Every criterion is verified by test and,
where it names a screen, in a real browser (agent-browser, via the sidebar) at 1280 and 375.

## S1 Filters and search

* AC-F1 The Filters popover offers Location, Agent, SO month, PO number and SPO number, each
  clearable, each written to the URL, each cleared by "Clear filters".
* AC-F2 `location=<code>` returns only rows whose Location column equals that code.
* AC-F3 `agent=<id>` returns only rows whose Agent column is that agent.
* AC-F4 `so_month=2026-03` returns only rows whose SO date falls in March 2026.
* AC-F5 `po_number=202605` returns every row with a PO link whose document starts with
  `202605`, and every row whose SPO link carries `source_po_number` starting with `202605`.
* AC-F6 `spo_number=SPO-2026/07` returns every row with an SPO link (own or derived) whose
  document starts with that text. Case-insensitive.
* AC-F7 Typing `202605-S0005` in the search box narrows to rows linked to that PO; typing an
  agent's name narrows to that agent's rows. The placeholder names PO, SPO and agent.
* AC-F8 `/summary` returns `locations` and `agents` facets with row counts; each facet ignores
  its own filter and honours the others.
* AC-F9 The Excel export honours every new param.

## S2 Month tabs, header, Schedule toolbar

* AC-M1 A tab strip renders between the cards and the toolbar: "All" first, then one tab per
  delivery month that has at least one row, in date order, each with its row count.
* AC-M2 Clicking a month tab sets `delivery_month` and the grid shows only that month; the
  tab reads selected; "All" clears it. The URL carries the value; reload keeps it.
* AC-M3 The Filters popover no longer offers a Delivery month select.
* AC-M4 The List / Schedule toggle sits in the page header's right slot on the same line as
  the title. No "Plan until" text renders anywhere on the page.
* AC-M5 The Schedule view shows the same search box, Filters button and month strip as the
  List view; typing in it narrows the matrix.
* AC-M6 At 375 the strip scrolls horizontally; the page body does not.

## S3 Schedule matrix

* AC-X1 `GET /order-inquiries/matrix` returns one cell per axis value and period; the qty of
  every cell for a product equals the sum of that product's rows in the list for that period.
* AC-X2 With 1,200 rows seeded across two years, the matrix shows every month, next year
  included; no row is missing.
* AC-X3 Week buckets start on Monday; `by=month` and `by=year` bucket on the first of the
  month / year.
* AC-X4 Each cell carries `buy`, `po`, `spo` stage sums; the drilldown for a cell lists
  exactly the rows summed into it.

## S4 Every row ticks; Action counts

* AC-T1 Every row whose state is not `cancelled` shows an enabled checkbox, fully linked rows
  included. The header checkbox ticks the whole page.
* AC-T2 With three rows ticked (one fully linked, one partly linked, one unlinked) the Actions
  menu reads "Link selected (2 of 3)", "Unlink selected (2 of 3)", "Reject selected (3 of 3)".
  When every ticked row is eligible the label reads "(3)".
* AC-T3 No menu item carries a second text line. The reason for a disabled item is a tooltip.
* AC-T4 "Link selected" posts `auto-place` with `row_ids` = the linkable ticked rows only;
  the toast states placed / skipped / after horizon counts; the list, cards and selection
  refresh.
* AC-T5 "Choose document (1)" is enabled only with exactly one ticked row and opens the
  manual link dialog for it.
* AC-T6 "Unlink selected" on a ticked fully linked row unlinks it (after the existing
  confirmation) and the row returns to `raised`.

## S5 Derived SPO, stage cards, cleanup

* AC-D1 A row linked to a PO line whose PO has an open SPO allocation for the same product
  shows that SPO number in the SPO column with a "via PO" tag; the lightbox lists it with
  "via PO".
* AC-D2 The derived SPO does not appear when the allocation is for another product, is
  received, or its shipment has landed.
* AC-D3 A row linked to an SPO shows the SPO's `from_po_number` in the PO column with a
  "via SPO" tag (today's behaviour, now marked).
* AC-D4 A PO-linked row with no SPO reads "awaiting shipment" in the SPO column; a row with no
  link reads a hyphen in both columns; "Not found (new order)" renders nowhere. A bundled row keeps
  its "Included with" headline.
* AC-D5 The cards read Buy, Purchased, Incoming in that order. A row of 8 on a PO line whose
  PO has a derived SPO of 5 contributes 5 to Incoming and 3 to Purchased and 0 to Buy.
* AC-D6 Pressing Incoming lists rows with a positive Incoming amount, derived ones included;
  pressing Purchased lists rows with PO qty not yet on a shipment; pressing Buy lists rows
  with unlinked qty. A row can appear under two cards only when its qty is split.
* AC-D7 `committed_v` and the reorder plan's demand are unchanged by a derived SPO (a derived
  SPO writes no link row).
* AC-D8 No card carries text under its number. No cell explains itself.
* AC-D9 The error code for an SPO placement refused by verb is
  `order_inquiry_spo_not_linkable`; no docstring in the service states that an SPO answers only
  an ORDER BACK row.

* AC-D10 A row of 8 on a PO line that also holds a real SPO link of 5 on the very allocation
  the PO derives counts Incoming 5, Purchased 3 (the derived twin of a real link is not added).
* AC-D11 A row of 10 with 3 on a PO line whose PO has an open allocation of 500 counts
  Incoming 3, Purchased 0, Buy 7 (derived cover capped at the PO-linked qty).
* AC-D12 A row of 20 over two PO lines of the same PO and product with one open allocation
  of 5 counts Incoming 5, Purchased 15 (an allocation is counted once per row).
* AC-D13 A row linked to two purchase orders, each with its own open allocation, lists both
  derived SPOs in `links[]`, and `spo_number=` finds the row by either.
* AC-D14 Under another company's scope the derived SPO of a Sorento allocation is neither
  listed, summed nor matched.
* AC-X6 The matrix stage sums equal the cards' rule per cell (a cell holding the AC-D11 row
  reads spo 3, po 0, buy 7).
* AC-X7 A cell's drilldown period covers the bucket's last day (a delivery on 30 April is in
  the April cell's drilldown; on 19 April in the week-of-13-April drilldown).

## S6 Planner

* AC-P1 "Plan selected" from the sales orders list opens the board on the List view; the URL
  carries no `view`; Grid writes `?view=grid`.
* AC-P2 One search box renders on the board, beside the title. The "Every contributing line"
  card has no search box of its own.
* AC-P3 Typing a customer name in that box narrows the List rows and the Grid rows alike
  (component test: the List view receives the search and renders only matching rows).

## B Browser evidence (agent-browser, via the sidebar)

* AC-B1 Procurement > Supply Chain > Order Inquiries: header toggle, month strip with counts,
  a month tab press, a PO number search, the Actions menu with "(a of n)" labels on three
  ticked rows, one fully linked row ticked and unlinked.
* AC-B2 Schedule: toolbar present, a search narrows the matrix, months of next year visible.
* AC-B3 Sales orders > tick one > Start > Plan selected: List view opens, one search box.
* AC-B4 A row with a derived SPO ("via PO") and its lightbox.
