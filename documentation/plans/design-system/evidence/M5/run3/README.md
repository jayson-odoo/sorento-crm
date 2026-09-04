# M5 browser evidence run 3

Lane: `feat/motion2-M5-shells-and-list-rules`, HEAD `c42c2358b` (three fix commits after
`eb7520461` "docs: M5 browser evidence run 2" - `cfbe91c12` skeleton fix, `eb15c7672`
notifications render-loop fix, `c42c2358b` page-restore fix). FE `http://localhost:3081`
(pre-existing, not started/restarted by this run), BE `http://localhost:8120`. Tool:
`agent-browser@0.27.0`, isolated `--session m5-run3`. Read-only throughout - no
Delete/Archive/Unlink/Confirm/Send/Save/Submit clicked on any real record, no deferred-action
countdown armed, no text typed into the conversation composer. On Users & Access > Settings >
Notifications, one Email checkbox was toggled and toggled back per the brief; Save was never
clicked.

Purpose: re-verify findings 1-3 from `documentation/plans/design-system/evidence/M5/run2/README.md`
(now fixed by the three commits above) and sweep the lists/sections they touched for regressions.

Note on navigation: sidebar-click navigation was used to reach every list/section fresh in this
run, per policy. Several sidebar row/tab clicks needed an explicit `scrollintoview` before the
click landed (targets below the viewport fold at 1280x800) - recorded once here rather than on
every row of the table below. One `open <url>` deep-nav was used to re-reach a Sales Order detail
page already visited earlier in the SAME session, purely to grab a second screenshot; every
first-time arrival at a section was via sidebar/topbar clicks.

## Results

| Check | Route | Viewport | Result | Numbers | PNG |
| --- | --- | --- | --- | --- | --- |
| 1. Crash fix - Packing Lists Proforma invoices, tab switch | Procurement > Packing Lists > "PL-2609-005" (`/procurement-management/packing-lists/{id}/proforma-invoices`) | 1280x800 | pass | 2 rows render, no pager, no error boundary; switched to Details tab and back to Proforma invoices - still 2 rows, no crash, `console`/`errors` clean | `01-packinglist-proforma-1280.png` |
| 1. Crash fix - Packing Lists Proforma invoices, hard reload | same URL, `agent-browser open` (full navigation, not soft) | 1280x800 | pass | Same 2 rows, no error boundary after a genuine full reload of the exact tab URL | (same PNG) |
| 1. Crash fix - Packing Lists Proforma invoices | same | 375x667 | pass | 2 rows, no error boundary at 375 | `02-packinglist-proforma-375.png` |
| 1. Crash fix - Orders lines card | Delivery Orders > "REP...-0484"-family record (`/order-management/orders/{id}`, `OrderLinesCard`) | 1280x800 | pass | 3 rows, no pager, no error boundary. (Note: the SCM "Sales Orders" module has a DIFFERENT, separately-paginated "Lines" tab - see the aside below the table; that one is out of this fix's scope and was not expected to be pager-free) | `03-orders-lines-1280.png` |
| 1. Crash fix - Purchase Request line items | Project Sales Admin > Purchase Requests > "PR26-0357" (`/procurement-management/purchase-requests/{id}`, `PurchaseRequestLineItemsGrid`) | 1280x800 | pass | 1 line item rendered ("**REPLACE", qty 1.00), no pager, no error boundary. This is the one record in the run with a non-empty grid on this exact `paginate={false}` component - the one run2 flagged as an unproven scope gap | `04-purchaserequest-lineitems-1280.png` |
| 2. Hang fix - Notifications idle | Users & Access > Settings > Notifications tab (`/user-management/settings/notifications`) | 1280x800 | pass | `MutationObserver` on `document.body` (childList+subtree+attributes+characterData), read after 5000ms real idle: **0 mutations** (pre-fix baseline per the fix commit: ~67,400 in 3s and climbing) | `05-notifications-settings-idle-1280.png` |
| 2. Hang fix - Notifications toggle responsiveness | same | 1280x800 | pass | Toggled Stock Alerts > Email checkbox: unchecked->checked (80 mutations recorded by the observer for that click), a `screenshot` immediately after returned normally (no 5s+ hang); toggled back checked->unchecked (49 more mutations), screenshot again returned normally; checkbox confirmed back to `checked=false`; Save never clicked | `06-notifications-after-toggle-1280.png`, `07-notifications-after-toggle-back-1280.png` |
| 3. Page restore fix (M5-07 core) - Products, in-app Back | Products page 2 (via People-style drilldown: Products > Products > All Products), row 38 "SRTBF11710" -> "Back to products" | 1280x800 | pass | Detail href carried `?page=2&limit=50&sort=created_at&dir=desc&from=e4f01fba-...`. After "Back to products": SAME url params, footer **"51 - 100 of 11672"**, exactly **1** `[data-returned="true"]` row and its text is SRTBF11710 | `08-products-backtolist-page2-1280.png` |
| 3. Page restore fix - Products, browser Back | Products page 2, row 38 re-opened -> browser Back | 1280x800 | pass | Same URL, same footer "51 - 100 of 11672", exactly 1 returned row (SRTBF11710) | `09-products-browserback-page2-1280.png` |
| 3. Page restore fix - Products | same flow (in-app Back variant) | 375x667 | pass | Footer "51 - 100 of 11672", 1 returned row, no clipping | `10-products-375-landing.png`, `11-products-375-backtolist-page2.png` |
| 3. Page restore fix - Delivery Orders (hand-rolled-ref list) | Delivery Orders page 2, row "REP202607-0483" -> "Back to delivery orders" | 1280x800 | pass | Detail href `?page=2&limit=50&...&from={id}`. After Back: same params, footer "51 - 100 of 27109", exactly 1 returned row | `12-orders-backtolist-page2-1280.png` |
| 3. Page restore fix - Contacts (hand-rolled-ref list) | Topbar apps-dropdown "Internal Users" (`/user-management/contacts` - documented as the ONLY nav path to this route, see `apps-dropdown-menu.tsx` comment) page 2, a row -> "Back to contacts" | 1280x800 | pass | Footer "51 - 76 of 76" both before and after; exactly 1 returned row after Back | `13-contacts-backtolist-page2-1280.png` |
| 3. Page restore fix - Sales Orders SCM (hand-rolled-ref list) | Supply Chain > Orders > Sales Orders (`/scm/sales-orders`) page 2, row "SO419122" -> "Back to sales orders" | 1280x800 | pass (page number); no `from=` on this route | Footer "26 - 50 of 14210" both before opening the detail and after Back; page number correctly restored to page 2. BUT this detail page's "Back to sales orders" link carries NO `from=`/`page=`-preserving highlight param at all (`href="/scm/sales-orders?page=2&limit=25&sort=order_date&dir=desc"`, no `from`) - `[data-returned="true"]` count is 0. This is a pre-existing gap in `SalesOrdersGrid`/its detail page (it never had the highlight wiring the other 3 lists have), not a regression from this fix - the fix's own job (page number restoring) is proven working here | `14-salesorders-scm-backtolist-page2-1280.png` |
| 4. Filter-reset regression - Products search | Products, page 2 | 1280x800 | pass | Typed "SRTBF" (via real keystrokes): dropped to page 1, footer "1 - 50 of 173" (filtered count). Cleared via select-all+Backspace initially got STUCK at the filtered count with no new network request fired (see Findings 1 below) - re-tested cleanly with type "X" (page 1, "1 - 50 of 4173") then one real `Backspace` keystroke: correctly returned to **page 1, "1 - 50 of 11672"** (full unfiltered count) | `15-products-search-drops-to-page1-1280.png`, `16-products-search-cleared-page1-1280.png` |
| 4. Filter-reset regression - Delivery Orders status filter | Delivery Orders, page 2 -> Status filter changed to "Shipped" | 1280x800 | pass (page reset); data anomaly noted | `page=1` correctly present in the fired request (`order_status_id=...&page=1`); footer read "1 - 0 of 0" for both "Completed" and "Shipped" status selections - 0 results for every non-"All" status tried in this dataset, which reads as a data/status-mapping issue unrelated to this fix, not a defect in the reset-on-filter-change mechanism (the page number reset is the thing under test and it worked) | `17-orders-statusfilter-page1-1280.png` |
| 4. Filter-reset regression - Purchase Orders selection clears | Supply Chain > Orders > Purchase Orders (`/scm/purchase-orders`), ticked 2 rows -> changed status radio Outstanding -> All | 1280x800 | pass | "2 selected" bar shown after ticking two rows; after changing the filter radio, the "N selected" text is gone entirely (selection cleared). No bulk action was clicked | `18-po-two-selected-1280.png`, `19-po-selection-cleared-1280.png` |
| 5. Regression spot check - Tickets sticky header | Footer "Support" link -> `/ticket-management/tickets` | 1280x800 | pass | `thead` computed `position: sticky`, `top` measured at 207px both before and after `container.scrollTop = 800` (unchanged); 50 rows rendered, no error boundary | `20-tickets-sticky-header-1280.png` |
| 5. Regression spot check - `paginate` PanelDataGrid still paginates at 10 | Products > several individual products' Purchase History tab | 1280x800 | inconclusive on the named page, pass via substitute | Every product tried in this dataset (VLDWT5879-GM, VLDWT8259-GM, SRTWT5879-BL, SRTWT902-GM-NL) has 0 or 1 purchase-history rows - none reached the >10 rows needed to prove the page-10 cap on this specific component. Substituted a DIFFERENT `paginate=true` PanelDataGrid instance already touched in this run - SCM Sales Order "Lines" tab, order `e9fb5508-...` - which correctly showed **"1 - 10 of 21"** with Previous/Next controls, confirming the default-pagination code path (untouched by the skeleton-count fix) still works | `21-product-purchasehistory-1row-1280.png`, `22-scm-so-lines-paginate10-1280.png` |

### Aside, not a fail: SCM Sales Order Lines tab paginates, unlike the order_management Orders lines card

Check 1's brief named "Orders > an order with lines > lines card" and run2's own A13 finding used
`/scm/sales-orders/{id}` (SO419417). That SCM route's "Lines" tab is a DIFFERENT component from
`OrderLinesCard.tsx` (which lives under `order-management/orders` and is one of the three
`paginate={false}` callers named in the SF-8 ruling / the skeleton fix). The SCM Sales Order Lines
tab has always been a normal `paginate=true` grid (10/page) and was never in scope for the crash
fix - it is not a regression, just a same-named-but-different component. This run's check 1 used
the `order_management` Delivery Orders route instead (matching the fix commit's own file list),
and confirmed 3 rows / no pager / no crash there.

## Findings for the captain

1. **agent-browser's `fill @ref ""` does not reliably clear a controlled React input in a way
   that fires a refetch.** During the Products search-reset check, `fill @e30 ""` (after
   `fill @e30 "SRTBF"`) left the DOM input's `.value` genuinely empty but the list stayed on the
   filtered "1 - 50 of 173" result with NO new `/api/v1/master-data/products` network request
   fired without a `query` param - `network requests --filter master-data/products` showed the
   last request was still `...&query=SRTBF`. A `Meta+a` + `Backspace` combo on the focused field
   also left it stuck the same way. The fix for the TEST (not the product) was to type a real
   character (`X`) then send one genuine `Backspace` keypress - that correctly triggered a fresh
   request and returned "1 - 50 of 11672" on page 1. This reads as an agent-browser/CDP quirk
   where a synthetic `fill` to empty-string does not always dispatch the input event a
   React-controlled field needs, not a product defect - flagging so the next agent doesn't waste
   time chasing a phantom "clear doesn't work" bug the way this run initially did.

2. **Delivery Orders' status filter returned 0 rows for every non-"All" option tried** ("Completed",
   "Shipped") in the current dev dataset. The page-reset mechanism under test worked correctly
   (`page=1` in the fired request both times), so this did not block check 4, but it is worth the
   captain's eye if anyone relies on this filter for anything else - possible drift between the
   status dropdown's option IDs and what is actually stamped on `orders` rows in this database.

3. **SCM Sales Orders' detail-page "Back to sales orders" link never carries a `from=` param**,
   unlike the other three hand-rolled-ref lists this run also checked (Delivery Orders, Contacts,
   and Products). `SalesOrdersGrid`/its detail page's return link is `?page=2&limit=25&sort=...&dir=...`
   with no highlight-restore param at all - `[data-returned="true"]` was 0 there by design, not by
   defect. The `page=` restore itself (this run's fix under test) worked fine on this route. Flagging
   because it means M5-07's "highlight the row you came from" promise has an existing gap on this
   one list that predates and is unrelated to the three commits under test in this run - worth its
   own ticket if the captain wants parity across all 26 lists.

4. **Could not find a product with more than 1 purchase-history row** in the current dev dataset
   to directly prove the Products > Purchase History tab still slices at 10/page after the
   skeleton-count fix (check 5's named target). Substituted the SCM Sales Order Lines tab (same
   `PanelDataGrid`, `paginate=true`, untouched by the fix) which cleanly showed "1 - 10 of 21" -
   reasonable but not identical evidence. Flagging so this is read as a data-availability gap in
   this run, not a clean pass on the literal named check (mirrors run2's own finding 6/A12 pattern
   of flagging scope gaps rather than silently passing them).

All three fixes under test (crash, hang, page-restore) reproduced clean on every check attempted,
including the three additional hand-rolled-ref lists beyond Products (Delivery Orders, Contacts,
Purchase Orders' selection-clear, and Delivery Orders' filter-reset). No new crash, hang, or
page-restore failure was found anywhere in this run.
