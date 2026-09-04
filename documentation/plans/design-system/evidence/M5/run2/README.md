# M5 browser evidence run 2

Lane: `feat/motion2-M5-shells-and-list-rules`, HEAD `685345d9a` (run 3 migrations + review fixes
landed on top of the `585462d76` briefed HEAD). FE `http://localhost:3081`, BE
`http://localhost:8120`. Tool: `agent-browser@0.27.0`, isolated `--session m5-run2`. Read-only
throughout - no Delete/Archive/Unlink/Confirm/Send/Save/Submit clicked on any real record, no
deferred-action countdown armed, no text typed into the conversation composer. The two
inline-editing forms (Purchase Requests New and Edit) were typed into and left without saving,
per the brief.

Contract: UAC M5-05, M5-06, M5-07,
`documentation/plans/design-system/ui-motion-round2-acceptance-criteria.md`. Run 1 evidence and
its README at `documentation/plans/design-system/evidence/M5/` (untouched).

Scope: walk the run-3 migration (24 raw tables now DataGrid, commits `9178f18c8`..`d54f41e39`)
and re-test M5-07 against the corrected wording (BL-2 review fix, commit `57efda364`).

Session note: the shared daemon hung THREE separate times during this run (Chromium renderer
pegged at ~110% CPU, every `agent-browser` command against that session timing out and getting
moved to background). Each time the session's own chrome + daemon processes were killed and
`open` re-run to get a fresh browser, then logged back in. One of the three coincides exactly
with a reproducible app bug (Findings 1) and is called out there; the other two (a
`get url`/`check` pileup early in the run, and a `scrollintoview`+`click` on System Health) are
recorded as environment flakiness since no matching console error or crash was ever printed for
them - `console`/`errors` came back clean both times. `get url` was checked before trusting any
read after each recovery.

## Results

| UAC | Route | Viewport | Result | Numbers | PNG |
| --- | --- | --- | --- | --- | --- |
| A1 Tickets list | `/ticket-management/tickets` (reached via the footer "Support" link - no sidebar entry exists, see e2e/tickets.spec.ts) | 1280x800 | pass | 50 rows render (906 total); row click opens `/ticket-management/tickets/{id}?page=1&limit=50&from={id}`; ticking 2 checkboxes leaves the URL unchanged (no navigation) and shows "Delete 2 selected"; pagination footer "1 - 50 of 906" with page buttons; sticky header measured scroller top=259 before AND after `scrollTop=1500` (unchanged); column resize dragged "Ticket #" 140px->240px (+100px, matches drag distance); column drag-reorder moved "Title" from position 2 to after "Updated" | `01-tickets-1280-selected.png`, `02-tickets-1280-resized.png`, `03-tickets-1280-reordered.png` |
| A1 Tickets list | same | 375x667 | pass | scroller top=375, height=347, bottom=722; toolbar (search/filters/view-toggle/Create Ticket) stacks cleanly, no overflow; grid horizontally scrollable, no clipping | `04-tickets-375-landing.png` |
| A2 MCP Tools | System > AI Assistant > MCP Tools (`/system-management/mcp-tools`) | 1280x800 | pass | 40 rows (of 40 total); sticky header scroller top=241 unchanged after `scrollTop=1000`; columns Tool/Module/Description | `05-mcptools-1280.png` |
| A2 MCP Tools | same | 375x667 | pass | "40 tools" counter, search + "Show deactivated" toggle stack cleanly, no clipping | `06-mcptools-375.png` |
| A3 Email Event Configs | System > Messaging > Email Event Configs (`/system-management/email-event-configs`) | 1280x800 | pass | 29 rows; sticky header top=274 unchanged after `scrollTop=800`; columns Event/Enabled/Rate override/Window override/Coalesce override/Actions | `07-emailconfigs-1280.png` |
| A3 Email Event Configs | same | 375x667 | pass | per-row toggle switches render, description text wraps cleanly, no clipping | `08-emailconfigs-375.png` |
| A4 App Store > Bundles | System > Platform > Module bundles (`/system-management/app-store/bundles`) | 1280x800 | pass | 4 rows (too few to prove a real scroll, but sticky-header markup and columns Order/Key/Display name/Modules/Actions confirmed present) | `09-bundles-1280.png` |
| A5 System Health Integrations | System > Operations > System Health (`/system-management/health`) | 1280x800 | pass | at the default 24h window only `n8n` (0 failed) shows, so no causes sub-row is visible; widened to 30d and got 8 channel rows including `respond_io` (386 success / 857 failed) with its causes sub-row rendered ALWAYS OPEN inline under the row (three lines: `200x 401 Client error...`, `176x 403 Client error...`, `148x 500`), no click/expand needed; `Benign`/`In flight` headers carry a real `title` attribute (`"Logged as a failure but expected..."` / `"Still in progress (pending/processing)"`); numeric header buttons all carry `justify-end` (visually right-aligned, confirmed in the screenshot) and every numeric data cell's inner span/div carries `text-right` | `10-systemhealth-integrations-30d.png` |
| A6 SLA Policies tiers + Users sheet | SLA > SLA Policies > "Reopen Policy" (`/sla-management/sla-policies/{id}`) | 1280x800 | pass | Tiers table (1 row, columns Tier Level/Tier Name/Response Hours/Resolution Hours/Users) renders; clicked "Users (20)" -> Sheet opened listing 10 of 20 users with Name/Email columns + its own pager; measured the sheet's DOM: exactly ONE element with `overflow-y:auto` AND `scrollHeight(730) > clientHeight(712)` (`div.flex-1.overflow-auto.py-4`) - ONE scrollbar | `11-slapolicy-tiers.png`, `12-slatiers-userssheet.png` |
| A7 Form SLA Config | SLA > Form SLA Configuration (`/sla-management/form-sla-config`) | 1280x800 | pass | Multiple `PanelDataGrid` sections, one per form type (Complaint 2 rows, Purchase Request 2+ rows, ...), each with its own sticky header and "Rows per page" footer; sticky header confirmed at scroller top=295 stable through a scroll | `13-formslaconfig.png` |
| A8 Teams > member table | User Management > People > Teams > "Customer Service" > Members (`/user-management/teams/{id}`) | 1280x800 | pass | 2 rows; columns Order/User/Auto-assign (round robin)/Actions; sticky header top=282 | `14-team-members.png` |
| A8 Settings > Notifications table | User Management > Settings > Notifications tab (`/user-management/settings`) | 1280x800 | **fail (browser hang)** | Table renders correctly (5 rows: Stock Alerts / New Delivery Orders / Delivery Order Status Updates / Payment Failures / System Errors; columns Notification/Users/Email/Web; per-row Users multi-select icon-button renders) - see screenshot. But clicking EITHER checkbox (Email or Web) on ANY row hangs the tab: the Chromium renderer process pegs at ~110% CPU indefinitely and every subsequent `agent-browser` command against that session times out (30-120s) until the session is killed and restarted. Reproduced twice, cleanly, immediately after a fresh login+navigate both times (see Findings 1) | `15-notifications-settings.png` |
| A9 Product tabs | Products > "VLDWT5879-GM" (`/master-data-management/products/{id}`) - Promotions / Purchase History / Stock tabs | 1280x800 | pass | Promotions: clean empty state ("No promotions linked to this product. Add this product to a promotion from Marketing -> Promotions."). Purchase History: 1 row, columns Date/PO Number/Supplier/Quantity/Received/Unit Cost, numeric cells (Quantity, Received, Unit Cost) confirmed `text-end`/`text-right` via inner span class. Stock: clean empty state ("No stock information available for this product. Stock records will appear here once inventory is added.") | `16-product-promotions-empty.png` |
| A10 Complaint fulfilment + attachments | Complaints > "CMPAPP-REJ-826265" (`/complaint-management/complaints/{id}`) - Fulfilment DOs tab + Details tab's Linked Attachments section | 1280x800 | pass | Fulfilment DOs tab: clean empty state ("No replacement delivery order linked yet.") inside a bordered card, no card-in-card double border. Linked Attachments (Details tab): clean empty state ("No linked attachments."). Neither section available with real data on the record tested; both empty states render correctly | `17-complaint-fulfilment-dos.png` |
| A11 Attachments detail modal + linkages | Resource Management > Files (`/resource-management/attachment-directories`) - click a file opens `AttachmentDetailModal` | 1280x800 | pass | Modal has "Attachment Details" / "Integration" tabs plus, further down inside the same scroll, a "Linkages" section with its own tab row (Products / Promotions / Forms / Packing Lists / Certificates) and a clean empty state ("No products linked to this attachment.") on the Products tab. Measured the dialog's DOM: exactly ONE element with `overflow-y:auto` AND `scrollHeight(1013) > clientHeight(640)` (`div.flex-1.min-h-0.overflow-y-auto.px-6.pb-6`) - ONE scrollbar for the whole modal, details AND linkages share it | `18-attachment-modal-linkages.png`, `19-attachment-modal-linkages-scrolled.png` |
| A12 GRN picking lines | Procurement > GRN > "SCM-SEED-GRN-004" (`/procurement-management/grn/{id}`) | 1280x800 | pass | 2 picking lines, columns SPO Allocation/Product/Location/Expected/Picked; client-side "Search product or warehouse" box: typing `CB2805A-DIY` filtered 2 rows down to 1 instantly (no network round trip) | (measured via `eval`, see `20`/`21` for the same page family) |
| A12 Packing Lists > Source proforma invoices | Procurement > Packing Lists > "PL-2609-005" and a second, unrelated record (`/procurement-management/packing-lists/{id}`) - Proforma invoices tab | 1280x800 | **fail (crash)** | Clicking the "Proforma invoices" tab throws `RangeError: Invalid array length` inside `<DataGridTableDnd>`, caught by the M5-04 error boundary (full shell survives: sidebar/topbar intact, "Something went wrong" card shown). Reproduced on TWO different, unrelated packing list records back to back - 100% reproducible, not data-specific. Root cause (read from source, see Findings 2): `SourceProformaInvoicesCard.tsx` passes `paginate={false}` to `PanelDataGrid`, which sets `pageSize: Number.MAX_SAFE_INTEGER` (`PanelDataGrid.tsx:165`); `useBodySkeleton()`'s truthy-only guard (`table.getState().pagination?.pageSize &&`, `data-grid-table.tsx:439`) does not protect against an astronomically large value, so while `isLoading && !hasRows` is true (every fresh mount, before the query resolves) `showBodySkeleton` is `true` and `Array.from({ length: pagination.pageSize })` (`data-grid-table.tsx:1284`) throws immediately | `20-packinglist-proforma.png`, `21-packinglist2-proforma-crash.png` |
| A12 Purchase Request line items + attachments | Procurement > Purchase Requests > "PR26-0369" (`/procurement-management/purchase-requests/{id}`) | 1280x800 | pass (scope note) | Both sections render clean empty states ("No line items." / "No linked attachments.") on the record tested and on 5 more stepped via the pager - none of the ~6 records reached had line items, so the SAME `paginate={false}` code path as the packing-list crash (`PurchaseRequestLineItemsGrid` in `PurchaseRequestDetail.tsx`, named in the SF-8 ruling) was never exercised with a real, non-empty grid here. Given the root cause in Finding 2 is generic to every `paginate={false}` `PanelDataGrid` caller whenever `isLoading && !hasRows`, and NOT specific to the packing-list's data, this is a scope gap in this run, not a clearance - the captain should not read this row as proof the PR line items grid is safe | (no dedicated PNG - see `22`/`23` for the same detail-page family) |
| A12 Stock Inquiries attachments | Procurement > Stock Inquiries > first record (`/procurement-management/stock-inquiries/{id}`) | 1280x800 | pass | Attachments section renders, no crash, no "Something went wrong" | `23-stockinquiry-attachments.png` |
| A13 Orders lines card | Supply Chain > Orders > Sales Orders > "SO419417" (`/scm/sales-orders/{id}`) - Lines tab | 1280x800 | pass | Every line rendered (no pager visible), columns Product/Qty ordered/Qty delivered/Outstanding qty/Linked to/Unit price; numeric columns (Qty ordered, Qty delivered, Outstanding qty, Unit price) all right-aligned in the screenshot | `22-order-lines.png` |
| A14 Inline editing, New Purchase Request | Procurement > Purchase Requests > Create (`/procurement-management/purchase-requests/new`) | 1280x800 | pass | Typed `5` into row 1's Qty; clicked "Add row"; row 1 still showed `5` after the new blank row 2 appeared (values: `["5",""]`); focused row 2's Qty input and typed `7` then `3` one keystroke at a time - `document.activeElement` stayed the SAME row-2 input both times (value went `7` -> `73`), no focus loss/remount. Left without saving (navigated to Purchase Requests list) | `27-loading-pr-new.png` (loading-shell shot; the typing itself has no dedicated PNG, see Findings for the eval transcript) |
| A14 Inline editing, Edit existing Purchase Request | Procurement > Purchase Requests > "PR26-0369" > Edit (`/procurement-management/purchase-requests/{id}/edit`) | 1280x800 | pass | Same focus-retention check on the edit form's line-items grid: typed `9` then `2` into the (blank, since the record has no lines) row-1 Qty one keystroke at a time - active element stayed the same input both times (value `9` -> `92`). Left WITHOUT saving (clicked "Purchase Requests" in the sidebar; no unsaved-changes prompt appeared, no Save/Submit was clicked) | (no dedicated PNG) |
| B1 M5-07 in-app "Back to list", page 2 | Products page 2, row 38 (`e4f01fba-...`) -> "Back to products" | 1280x800 | **fail** | Detail href correctly carried `?page=2&limit=50&sort=created_at&dir=desc&from=e4f01fba-...`. Clicked "Back to products": URL became `?page=2&limit=50&sort=created_at&dir=desc&from=e4f01fba-...` (correct, unlike run 1) BUT the grid rendered PAGE 1 content (`row1 = "VLDWT5879-GM..."`, the same product that opens page 1 by default; "Go to previous page" was `disabled=true`; footer read "1 - 50 of 11672"). `document.querySelectorAll('[data-returned="true"]')` found ZERO rows - the target row is on the real page 2 and is simply never rendered, so it cannot be centred or highlighted. Waited 1.5s and re-checked - no change | `24-products-backtolist-page1-instead-of-2.png` |
| B2 M5-07 browser Back, page 2 | Products page 2, row 38, re-opened -> browser Back | 1280x800 | **fail** | Same shape as B1: after Back, `get url` correctly reports `?page=2&limit=50&sort=created_at&dir=desc&from=e4f01fba-...` (the BL-2 history-rewrite fix IS working - the URL is right), but the rendered grid is page 1 again (`row1 = "VLDWT5879-GM..."`, 0 returned rows). Escalated the check: opened that EXACT URL fresh (`agent-browser open`, a hard navigation/full reload, not a soft nav) - STILL page 1, still 0 returned rows, even after a 2s wait. This proves the bug is not a soft-navigation state-sync issue - the `page` query param is never consumed to initialize the grid's pagination state on ANY kind of load | `25-products-browserback-page1-instead-of-2.png` |
| B3 M5-07 detail pager x3 then in-app Back | Products, row 10 (page 1) -> "Next product" x3 -> "Back to products" | 1280x800 | pass | Every pager step kept `from=` matching the new landing product (per M5-07's documented shape - `router.push` per step). One click of "Back to products" from the 4th product landed on `?page=1&limit=50&sort=created_at&dir=desc&from=b163541d-...` and `[data-returned="true"]` found exactly 1 row (`"SRTWT5879-BL..."`), scrolled into view and highlighted. Because the reader started AND stayed on page 1 throughout (the pager never touches the list's `page`), this is the one shape where B1/B2's bug cannot manifest - it confirms the `from=`/highlight restore mechanism itself is correct, and isolates the defect specifically to a non-1 `page` value never being honored | `26-products-b3-pager-backtolist-pass.png` |
| B4 M5-07 regression check, extra param survives | `/master-data-management/products?zzt_marker=1` (deep URL, explicitly allowed) -> click row 1 -> browser Back | 1280x800 | pass | Detail href: `.../products/0111ede4-...?page=1&limit=50&from=0111ede4-...` (no `zzt_marker`, correct - it is not a reserved list-state key). After Back: `?zzt_marker=1&page=1&limit=50&from=0111ede4-...` - the invented param survived alongside the reserved keys, proving the BL-2 fix seeds the rewrite from the list's CURRENT params rather than replacing them wholesale | (no dedicated PNG - single-line URL check) |
| B5 M5-07 embedded grid, host page not clobbered | Master Data > Product Specifications > "brand" (`/master-data-management/product-specifications/brand`) > "Seen in products" tab -> click a product row -> browser Back | 1280x800 | pass | URL before the click: `.../product-specifications/brand?page=1&limit=57&sort=label&dir=asc&from=brand`. Click opened `/master-data-management/products/6733068a-...?page=1&limit=25&tab=specifications&back=%2Fmaster-data-management%2Fproduct-specifications%2Fbrand&from=6733068a-...` (a DIFFERENT top-level route, `SeenInProductsTab`'s own `rowHref`). After browser Back: URL was IDENTICAL to before the click, byte for byte (`...brand?page=1&limit=57&sort=label&dir=asc&from=brand`) - NOT rewritten with the tab's own `page=1&limit=25`, confirming the BL-2 "only rewrite when the href is a child of the current pathname" rule holds | (no dedicated PNG - single-line URL check) |
| C loading shell, Purchase Requests > New | `/procurement-management/purchase-requests/new` | 1280x800 | not verifiable (too fast) | Fully rendered form by the time the screenshot fired; no skeleton caught. One title bar ("New Purchase Request"), no duplicate | `27-loading-pr-new.png` |
| C loading shell, MCP Tools | `/system-management/mcp-tools` | 1280x800 | not verifiable (too fast, but caught a transient data state) | Caught a moment where the Card chrome ("MCP Tools Catalog", search box, column headers) had already painted but the query hadn't resolved yet ("0 tools" / "No tools match." shown transiently) - this is the section's OWN empty-vs-loaded flicker, not a `ListPageSkeleton` row-bar skeleton. One title area, no duplicate | `28-loading-mcptools.png` |
| C loading shell, System Health | `/system-management/health` | 1280x800 | not verifiable (too fast) | Fully rendered (all 4 cards + Integrations table) by the time the screenshot fired. One title bar, no duplicate | `29-loading-systemhealth.png` |
| C loading shell, Tickets | `/ticket-management/tickets` (via footer "Support" link) | 1280x800 | pass (caught mid-load) | Real chrome painted immediately (title "Tickets", breadcrumb, search/filter toolbar, view toggle, "Create Ticket" button all real, not skeletal) while the GRID BODY showed per-cell skeleton bars (grey pill shapes) in the Status/Priority columns for 7 visible rows - this is `DataGridTable`'s own `showBodySkeleton` path (`data-grid-table.tsx:1283`), not the route-level `ListPageSkeleton`. One title bar, no duplicate | `30-loading-tickets.png` |
| C loading shell, Settings > Notifications | `/user-management/settings` (Notifications tab) | 1280x800 | not verifiable (too fast) | Fully rendered (client-side settings-context data, no async fetch) by the time the screenshot fired. One title bar ("Settings"), no duplicate | `31-loading-notifications-settings.png` |

## Findings for the captain

1. **Settings > Notifications table: clicking either checkbox (Email or Web) on any row hangs
   the tab.** Reproduced twice, both times immediately after a fresh login and navigate straight
   to `/user-management/settings` > Notifications tab > click one checkbox. Both times the
   Chromium renderer process for the session pegged at ~110% CPU and stayed there; every
   subsequent `agent-browser` command against that session (including a plain `screenshot`)
   timed out (15-120s) until the session's chrome + daemon processes were killed and restarted.
   `console`/`errors` after the SECOND recovery came back completely clean - no error, no
   warning, nothing printed before or after the hang, which rules out a simple uncaught
   exception and points at a genuine infinite loop or runaway re-render triggered by the
   checkbox's `onCheckedChange` (`app/(protected)/user-management/settings/notifications/page.tsx:268,296`,
   a plain react-hook-form `FormField`/`Controller` + `Checkbox`). The "roles" column in the
   same table's `columns` `useMemo` calls `form.watch(roleIdsField)` directly inside the cell
   renderer (`page.tsx:200`) rather than via the `useWatch` hook - not the cell that hung, but
   worth the captain's eye since it is the one non-standard read in this table and re-runs the
   watch on every render. Did not have budget in this run to bisect further; flagging as the
   single reproducible, unresolved bug in this table.

2. **Packing Lists > Proforma invoices tab crashes 100% of the time, on any record.**
   `RangeError: Invalid array length` thrown inside `<DataGridTableDnd>`, caught cleanly by the
   M5-04 error boundary (full shell survives - this is the ONE useful side effect: M5-04 is
   proven live a second time, on a genuinely new component). Root cause, read from source, not
   guessed:
   - `SourceProformaInvoicesCard.tsx:190` passes `paginate={false}` to `PanelDataGrid`.
   - `PanelDataGrid.tsx:161-165` sets `pagination.pageSize` to `Number.MAX_SAFE_INTEGER` whenever
     `paginate` is `false` (the SF-8 review ruling's own mechanism, documented in its own
     comment: "TanStack's pagination row model slices by index, so an oversized page size is
     just 'every row'").
   - `data-grid-table.tsx`'s `useBodySkeleton()` (line 432-441) decides whether to draw skeleton
     rows. Its guard is `table.getState().pagination?.pageSize && ...` - a plain truthiness
     check. `Number.MAX_SAFE_INTEGER` is truthy, so the guard does NOT catch it; the guard only
     ever protected against `pageSize` being `0`/`undefined`.
   - When `isLoading && !hasRows` (true on every fresh mount before the query resolves - which
     is every single time a reader opens this tab, not just cold loads), `showBodySkeleton`
     evaluates `true`, and line 1284 runs `Array.from({ length: pagination.pageSize }).map(...)`
     - `Array.from({ length: Number.MAX_SAFE_INTEGER })` throws `RangeError: Invalid array
     length` immediately.
   - The same file's own comment two lines above (`data-grid-table.tsx:429-430`) states outright:
     *"The `pageSize` clause is what makes those render paths safe to write `Array.from({ length:
     pagination.pageSize })` without re-testing it."* - the clause does not, in fact, make it
     safe for this value.
   - **This is not specific to `SourceProformaInvoicesCard`.** The SF-8 ruling in the UAC names
     THREE callers of `paginate={false}`: `OrderLinesCard.tsx`, `PurchaseRequestDetail.tsx`
     (`PurchaseRequestLineItemsGrid`), and `SourceProformaInvoicesCard.tsx`. Only the packing-list
     card was caught crashing in this run because it was the only one of the three landed on
     while its query was still genuinely loading with zero cached rows - `OrderLinesCard` (A13)
     and the Purchase Request line-items grid (A12) both happened to render past this window
     without incident on the records this run reached (Orders' data likely arrives bundled with
     the parent document fetch; every Purchase Request record reached in this run had zero line
     items, an early-return empty-state path that may not even mount the grid). **The fix belongs
     in `useBodySkeleton()`'s guard** (e.g. `Math.min(pagination.pageSize, someSaneCap)` or an
     explicit `pageSize !== Number.MAX_SAFE_INTEGER` check), not in any one caller, since every
     future `paginate={false}` `PanelDataGrid` will hit the same wall the moment its query is
     genuinely still loading with no rows.

3. **B1/B2: the in-app "Back to list" button and the browser's native Back button both fail to
   restore a non-1 page.** The BL-2 review fix (commit `57efda364`) is confirmed working
   correctly at the URL level in both directions - `page`, `limit`, `sort`, `dir` and `from` all
   arrive in the address bar exactly as documented, and a hard hard-reload at that exact URL was
   used to rule out a soft-navigation timing issue. But the DataGrid component itself never
   reads the URL's `page` param to seed its own pagination state on mount, under ANY navigation
   kind (Link click, browser Back, or a cold full-page load at the URL) - it always starts at
   page 1 (`pageIndex: 0`). Because the M5-07 restore mechanism (`useReturnedRowId` /
   `data-returned`) only ever looks at ROWS THE TABLE ACTUALLY RENDERED, and the target row from
   page 2 is never in that render, the highlight/centre-into-view effect silently never fires -
   no error, no console warning, just nothing happening. Check B3 isolates this precisely: the
   SAME restore mechanism DOES work, in one press, when the reader never left page 1 (the
   detail-pager case never touches the list's own `page`). The fix is a page-1-only regression
   in disguise - anyone testing M5-07 by starting from a short list, or from page 1 of a long
   one, would see it pass every time. The captain should treat B1/B2 as still open against the
   corrected wording, not fixed by the BL-2 patch that WAS verified working (B4, B5).

4. **Sidebar accordion buttons toggle CLOSED on a second click even when read as `aria-expanded:
   "true"` moments earlier**, and clicking an item scrolled below the viewport fold is a silent
   no-op (not specific to this branch - a tooling/navigation-discipline note, not a product bug).
   Cost real time in this run: `.click()` via `page.evaluate` does not scroll a target into view
   first, so several sidebar submenu items 1000+px down the accordion needed an explicit
   `scrollIntoView` before the click landed. Recorded here so the next agent on this shared
   daemon does not re-lose the same twenty minutes.

5. **Tickets has no sidebar entry anywhere in the app** - reached only via the dashboard footer's
   "Support" link (confirmed against `e2e/tickets.spec.ts:57-67`, which documents this as the
   intended path: *"Plan step 1: footer Support link goes to the ticket list."*). Not a defect
   (this is the existing, intentional design, not something M5 touched), but worth noting since
   the brief's "Ticket Management > Tickets" sidebar path does not exist to walk.

6. **A5's Integrations table shows no channels at all in the default 24h window** in this dev
   data (`n8n`, 0 failed) - the causes-sub-row check could only be exercised by widening to 30d.
   Not a defect, just a data-availability note for whoever re-runs this against a different
   database.
