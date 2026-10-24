# Browser evidence walk: oi-worklist-excel-parity

Lane branch `feat/oi-worklist-excel-parity`, worktree
`.claude/worktrees/oi-worklist-excel-parity`. Stack: frontend `http://localhost:3086`, backend
`:8086`, shared dev DB with real order-inquiry rows. Driven with `agent-browser@0.27.0`,
`--session oiwl` (isolated from other agents on the shared daemon). Navigated by sidebar clicks
from `http://localhost:3086/` throughout: Procurement > Supply Chain > Order Inquiries; Project
Sales Admin > Sales Orders. Date of run: 2026-09-16.

One mid-run auth drop occurred (session cookie expired, redirected to `/signin`) after the first
"Clear filters" investigation; re-logged in with the same E2E credentials and resumed on the same
page. Noted where relevant below.

## AC-by-AC results

**AC-B1 / M1 / M2 / M3 / M4 / T1 / T2 / T3 / T5 / T6 / D4 / D8 (Order Inquiries screen)**

- Header toggle (List/Schedule) renders on the same line as the "Order inquiries" title, right
  slot. No "Plan until" text anywhere on the page (`document.body.innerText.includes('Plan
  until')` -> `false`). **PASS.** Screenshot: `walk-01-list-header.png`.
- Month strip: "All" renders first (highlighted blue by default), then one tab per delivery
  month with a row count, in ascending date order (MAR 06 (1), DEC 24 (1), FEB 25 (1), APR 25
  (2), ... through DEC 26, then JUNE 27, JULY 27). **PASS.** Screenshot:
  `walk-02-month-strip-start.png`.
- Clicking a month tab (JAN 26) sets `?delivery_month=2026-01` in the URL and the grid narrows
  (cards changed from Buy 288227/Purchased 13864/Incoming 20446 to Buy 7588/Purchased 728/
  Incoming 3340, confirmed via network `GET .../order-inquiries?...&delivery_month=2026-01` and
  `.../summary?delivery_month=2026-01`). A full page reload (`location.reload()`) kept the param
  and the filtered state. Clicking "All" cleared `delivery_month` from the URL. **PASS** (all
  three sub-checks).
- Filters popover fields, confirmed via full accessibility snapshot: Location, Agent, SO month,
  PO number, SPO number, plus pre-existing Linked / Confirmed / Supplier / Project / Raised by /
  Raised on. **No Delivery month field present.** **PASS.**
- Ticked three rows (one unlinked - SO369758/MCM7833-CR; one PO-linked - SO324265/SRT8304; one
  SPO-linked ("via SPO") - SO338571/CB6624). All three checkboxes were enabled (not disabled;
  fully-linked row included). Opened Actions: `Choose document (1)` disabled, `Link selected (0
  of 3)` disabled, `Unlink selected (1 of 3)` enabled, `Reject selected (1 of 3)` enabled,
  `Unlink all...`, `Export Excel`. Each menu item is a single line in the DOM (`textContent`
  matches the visible label exactly, no second line). The two disabled items carry a `title`
  attribute ("Tick exactly one row to choose its document by hand." / "Tick rows still needing a
  document to link.") - i.e. the disabled reason is a native tooltip, not on-page text.
  **PASS** (AC-T1, T2, T3). Screenshot: `walk-17-actions-menu-3ticked.png`.
- With exactly one row ticked (the PO-linked SO324265), `Choose document (1)` was enabled and
  clicking it opened the "Link to a document" dialog scoped to that row. **PASS** (AC-T5).
  Screenshot: `walk-18-choose-document-dialog.png`.
- With that same single fully-linked row (SO324265, PO `202606-S0033`, Qty 23, Taken 23,
  Remaining 0) still ticked, ran `Unlink selected (1)` through its confirmation dialog ("Unlink
  selected" heading, Cancel / Unlink buttons - confirmation is present, consistent with
  unlink-is-not-hard-delete). `POST .../order-inquiry-rows/{id}/unplace` returned 200. After: PO
  cell -> "-", SPO cell -> "-", Remaining -> 23, Taken -> 0; cards moved Buy 288227 -> 288250
  (+23) and Purchased 13864 -> 13841 (-23), i.e. the row rejoined the unlinked/raised bucket.
  **PASS** (AC-T6). Screenshots: `walk-19-after-unlink.png`.
  Then re-ticked the same row and ran `Link selected (1)` (`POST .../auto-place` returned 200);
  the row's PO/SPO/Taken/Remaining and the three cards returned to their exact starting values
  (Buy 288227, Purchased 13864). **Shared dev data was restored to its original state.**
  Screenshot: `walk-20-relinked.png`.
- `document.body.innerText.includes('Not found (new order)')` -> `false` throughout. **PASS**
  (part of AC-D4).
- PO/SPO columns (viewed at 1920x1000 with Project/Customer, Supplier, Agent, Location columns
  hidden via Columns menu to fit): a PO-linked row with no SPO reads "awaiting shipment" in the
  SPO column; an unlinked row reads "-" in both PO and SPO. **PASS** (AC-D4, minus the "bundled
  row keeps its Included with headline" clause - no bundled row was found in the rows surfaced by
  this walk, see Not Testable below). Screenshot: `walk-10-wide-view.png`.
- No card (Buy/Purchased/Incoming) carries a caption/second line under its number, confirmed in
  every full-page screenshot of the List header. **PASS** (AC-D8).

**AC-F7 (search box)**

- Placeholder reads "Search S/O, item, PO, SPO, customer, agent" (names PO, SPO and agent).
  **PASS.**
- Typed `202605` (a real PO prefix from the PO column): list narrowed, `GET
  .../order-inquiries?...&query=202605` fired, all visible rows carried a PO or SPO number
  starting `202605`. **PASS.** Screenshot: `walk-04-search-po.png`.
- Typed `JUSTIN` (an agent name from the Agent column): list narrowed (cards changed to Buy
  31309/Purchased 1758/Incoming 2460), `GET .../order-inquiries?...&query=JUSTIN` fired. **PASS.**
  Screenshot: `walk-33-agent-search.png`.

**AC-F1 (Filters: Location, Agent, clear)**

- Opened Filters, selected Location = `BRW-BB (3665)`: `GET
  .../order-inquiries?...&location=BRW-BB` fired (correct data), Filters button badge changed
  from `Filters` to `Filters 1`. Then selected Agent = `BRENDON`: `GET
  .../order-inquiries?...&location=BRW-BB&agent=<uuid>` fired, badge -> `Filters 2`. **Badge count
  follows selections correctly (PASS).**
- **FAIL: the Location and Agent filter values are never written to the page URL.**
  `location.search` stayed `?ack=all` throughout (checked with `location.href` / `location.search`
  directly, independent of viewport), even though the same-shaped `delivery_month` and `query`
  params reliably appear in the URL for the month-tab and search-box filters on this same screen.
  A reload while these filters were active would silently drop them (contrast with
  `delivery_month`, which survives reload). This contradicts AC-F1's "each written to the URL".
  Screenshot: `walk-21-location-filter-badge.png` (badge reads "Filters 1" while the address bar
  still reads `?ack=all`).
- "Clear filters" does reset both fields (Location back to "Every location", Agent back to
  "Every agent") and the badge returns to plain "Filters" - confirmed once the popover's own
  "Clear filters" button was actually visible in the viewport (it sits at the bottom of a tall
  popover; the button must be scrolled into view or a taller viewport used, or the click lands on
  nothing and looks like the button is inert - noted as a false-negative trap for future runs, not
  a product defect). **PASS** once clicked correctly.

**AC-B2 / M5 / M6 / X2 (Schedule)**

- Same toolbar (search box, Filters button, Columns, month strip) renders on the Schedule view as
  on List. **PASS.** Screenshot: `walk-25-schedule-loaded.png`.
- Typing `CB6624` into the search box narrowed the matrix to that one product row and fired
  `GET .../order-inquiries/matrix?query=CB6624&axis=product&by=month`; cells for that product
  showed correct stage breakdowns ("SPO 130", "PO 95", "Buy 104 - PO 168"). **PASS** (AC-M5, and
  supports AC-X4's per-cell buy/po/spo sums).
- Scrolled the matrix horizontally to its full width at 1280px: months through Dec 2026 then
  Jun 2027 and Jul 2027 are present and populated (e.g. B2155-NL-BLUE showing "142 / PO 142" in
  Jul 2027). **PASS** (AC-X2). Screenshot: `walk-27-matrix-scrolled-2027.png`.
- At 375x800: the month strip's own container has `scrollWidth` 2756 vs `clientWidth` 343
  (scrolls horizontally), while `document.documentElement.scrollWidth` (375) equals
  `clientWidth` (375) - the page body does not scroll sideways. **PASS** (AC-M6). Screenshot:
  `walk-28-mobile-schedule.png`.

**AC-D1 / D3 (derived SPO tags + lightbox)**

- Searched `202605` with Project/Customer + Supplier columns hidden: multiple rows show a PO
  number in the PO column and, in the SPO column, `SPO-2026/07-0064` tagged "via PO". Clicking
  that SPO cell opened a "Backing documents" lightbox listing `PO 202605-S0005` (47 units) and
  `SPO SPO-2026/07-0064 via PO` (13 units) - the "via PO" tag is present inside the lightbox too.
  **PASS** (AC-D1, AC-B4). Screenshot: `walk-14-via-po-lightbox.png`.
- Searched `SPO-2026`: multiple rows show a PO number in the PO column tagged "via SPO"
  (e.g. `202511-S0026 via SPO`), consistent with a row linked directly to an SPO whose
  `from_po_number` is surfaced in the PO column. **PASS** (AC-D3). Screenshot:
  `walk-12-via-spo-results.png`.

**AC-B3 / P1 / P2 / P3 (Sales Orders -> Plan selected -> board)**

- Sales Orders list (Project Sales Admin > Sales Orders): ticked one order (SO419522), clicked
  "Start", menu showed "Upload sales orders" / "Plan selected (1)". Clicked "Plan selected (1)":
  landed on `.../project-sales/fulfilment-planning?orders=SO419522&sort=...` with **no `view`
  param**, and the List toggle was the highlighted/active one. **PASS** (AC-P1, AC-B3).
- Exactly one search box renders on the board, in the header row beside the "Planning 1 sales
  orders together" title (`Search sales order, customer, project or product`). The "Every
  contributing line" card only has sort/collapse icon buttons, no search box of its own.
  **PASS** (AC-P2). Screenshot: `walk-29-planner-list.png`.
- Typed `C-FH14` (a product code, standing in for "narrows by name" - a customer-name search
  would exercise the identical control): List rows narrowed from many to "1 - 1 of 1". Clicked
  "Grid": URL became `...&product=C-FH14&view=grid`, and the Grid view also narrowed to the same
  single product/row. **PASS** (AC-P3, AC-P1's `view=grid` clause).
  Screenshots: `walk-31-planner-search-narrow.png` (List, filtered) / `walk-32-planner-grid.png`
  (Grid, filtered, `view=grid` in the URL).

## Console / errors

- One pre-existing warning seen on every page of this app shell, unrelated to this lane:
  `[error] Each child in a list should have a unique "key" prop... Check the render method of
  \`Demo1Layout\`.` This is the Metronic shell layout component, not anything touched by this
  slice. No other console errors or uncaught page errors were observed across List, Schedule,
  the lightbox, the Actions menu flows, or the planner board.
- One mid-walk incident: the browser session's URL went to `about:blank` and then to `/signin`
  (JWT/session expiry) partway through the Filters investigation. Re-logged in with the same
  E2E credentials and resumed; not a product defect, noted for the record since it interrupted
  one Clear-filters attempt (see AC-F1 notes above about the popover scroll trap).

## Not testable in this walk

- **AC-D4's "a bundled row keeps its Included with headline"** - no row surfaced by the searches
  run in this walk (`202605`, `SPO-2026`, `JUSTIN`, `CB6624`) showed "Included with" text; the
  overall `document.body.innerText` check for that literal string was not run against every
  possible row combination, only the states directly navigated to. Not exercised; needs a
  bundled-row fixture to confirm.
- **AC-T4's toast wording** ("placed / skipped / after horizon counts") - the `auto-place` and
  `unplace` POSTs were confirmed at the network layer (200 responses, correct before/after grid
  state), but the toast text itself was not captured in a screenshot at the moment it appeared.

## Summary

| AC | Result |
| --- | --- |
| B1, M1, M2, M3, M4 | PASS |
| T1, T2, T3, T5, T6 | PASS |
| D1, D3, D4 (minus bundled-row clause), D8 | PASS |
| F7 | PASS |
| F1 (badge, clear) | PASS |
| **F1 (written to URL for Location/Agent)** | **FAIL** |
| B2, M5, M6, X2 | PASS |
| B3, B4, P1, P2, P3 | PASS |
| T4 (toast wording) | Not directly captured (network-level PASS) |
| D4 (bundled row headline) | Not testable in this walk |

One reportable defect: **Location and Agent filters (and by extension SO month / PO number / SPO
number, not individually re-checked here but sharing the same popover-apply code path) do not
write to the URL**, unlike `delivery_month` and the free-text search `query`, which do. A reload
while a Location or Agent filter is active silently loses it. This should go back to the coder
before the lane is called done on AC-F1.
