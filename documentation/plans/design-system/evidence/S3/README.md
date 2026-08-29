# S3 Phase 1 browser verification - detail header, action parity, page-scoped pager

Verified against `apple-alignment-acceptance-criteria.md` (S3-01 to S3-07, D3-D6, D15) and
`PLAN-apple-alignment.md` 3.3/3.4. Worktree `agent-a4fcc3bb35ba62b83`, branch
`feat/apple-S3-detail-header-pager`, FE `http://localhost:3090`, BE `http://localhost:8000`.
Entities wired in Phase 1: Users, Delivery Orders, Products. agent-browser 0.27.0, headless,
`--session s3-evidence`. Login via `E2E_EMAIL`/`E2E_PASSWORD`. No records created, saved or
deleted; all Delete/Trash menu items were opened for inspection then closed with Escape, never
confirmed.

## Result table

| AC | Pass/Fail/Unverified | Screenshot | Note |
|----|----|----|----|
| S3-01 (Users) | Pass | S3-01-users-toolbar-1280.png | Toolbar = title "User" + breadcrumb left, one "Back to users" right. Back href `?page=1&limit=10&sort=name&dir=asc`. |
| S3-01 (Delivery Orders) | Pass | S3-01-S3-02-do-toolbar-1280.png | Back href carries `page`, `limit` AND the active `order_status_id` filter (key-parity risk item 6, confirmed). |
| S3-01 (Products) | Pass | S3-01-S3-02-products-toolbar-1280.png | Back href carries `page`, `limit`, `sort`, `dir` AND the active `category_id` filter. |
| S3-02 record card order (Users/DO/Products) | Pass | S3-01-users-toolbar-1280.png, S3-01-S3-02-do-toolbar-1280.png, S3-01-S3-02-products-toolbar-1280.png | All three: pager, gear, one primary button, left to right. |
| S3-02 gear = secondary, separator, Delete last red (Users) | Pass | S3-02-users-gear-1280.png | Impersonate user, Send invitation link, separator, "Trash user" red last. |
| S3-02 gear (Delivery Orders) | Pass | S3-02-do-gear-1280.png | "Mark as Picked Up / In Transit", separator, "Delete delivery order" red last. |
| S3-02 gear (Products) | Pass | S3-02-products-gear-1280.png | Only "Delete product" (no secondary items on this record) - correctly still red, still last. |
| S3-02 list "..." = same items same order as gear (Users) | Pass | S3-02-users-rowmenu-1280.png | Identical to S3-02-users-gear-1280.png. |
| S3-02 list "..." parity (Delivery Orders) | Pass | S3-02-do-rowmenu-1280.png | Identical order to record gear. |
| S3-02 list "..." parity (Products) | Pass | S3-02-products-rowmenu-1280.png | Identical order to record gear. |
| S3-03 pager counter "n/pageSize", no extra request (Users) | Pass | (network eval, no screenshot) | Row 3 of a `limit=10` `sort=name` list opened as "3 / 10"; `performance.getEntriesByType('resource')` count for `/api/v1/user-management/users?` stayed at 2 before and after opening the detail. |
| S3-03 (Delivery Orders, status filter active) | Pass | (network eval) | Row 3 of a `New Order`-filtered, `limit=50` list opened as "3 / 50"; list-endpoint resource count unchanged (5 before, 5 after Next). |
| S3-04 Next/Previous walk + fetch-once at page boundary (Users) | Pass | (network eval) | 7x Next from 3/10 landed on 10/10, zero new `/users?` requests. One more Next crossed to page 2 ("1/10"), fired exactly one new request (`page=2`). Previous from there returned to page 1 landing on "10/10" with no further request (cache reuse). |
| S3-04 Previous disabled at page 1 row 1 | Pass | (eval, `.disabled` read) | Walked back to "1 / 10"; `Previous`.disabled === true, `Next`.disabled === false. |
| S3-04 Next disabled at the true last page's last row | Unverified | - | The dev DB's Users table has hundreds of scripted `test.local` rows (pytest leftovers); stepping Next reached page 207+ (2000+ users) without disabling. Impractical to reach the genuine end in this session. Boundary *mechanism* is verified by symmetry (start boundary above, and 200+ consecutive page-crossings all fetched exactly once with no errors). |
| S3-05 reload/deep link keeps pager | Pass | S3-05-users-deeplink-1280.png | Reopened `/user-management/users/<id>?page=1&limit=10&sort=name&dir=asc` fresh; pager read "3 / 10" immediately. |
| S3-05 `page=999` hides pager, Back still works | Pass | S3-05-users-page999-1280.png | Pager area gone (only gear + Edit remain); "Back to users" present and functional. |
| Item 6: DO with status filter | Pass | S3-01-S3-02-do-toolbar-1280.png | Covered above; `order_status_id` rides in both the row href and the Back href. |
| Item 6: Products with category filter | Pass | S3-01-S3-02-products-toolbar-1280.png | Covered above; `category_id` rides in both. |
| Item 7: row click opens detail | Pass | - | Confirmed on Users/DO/Products throughout the run. |
| Item 7: Enter on a focused row opens it | Pass | - | Focused a Users row (real DOM focus, `tabindex="0"`), pressed Enter via the tool, navigated to that row's detail. |
| Item 7: middle-click opens a new tab | **Fail** | - | See "Failures" below. `window.open` fires correctly with the right href, `_blank`, `noopener,noreferrer` - but the **current tab also navigates** to the same URL, which is not middle-click semantics. |
| S3-02 at 375 - wraps under identity, nothing clipped (Users) | Pass | S3-02-users-detail-375.png | Pager/gear/Edit user drop to their own row below the avatar+name; no clipping. |
| S3-02 at 375 (Delivery Orders) | Pass | S3-02-do-detail-375.png | Same wrap pattern. |
| S3-02 at 375 (Products) | Pass | S3-02-products-detail-375.png | Same wrap pattern (pager absent here because the deep-link URL I used dropped the original `sort`/`category_id`, which is itself a correct S3-05 "record not on this page's cache key" case, not a bug). |
| Item 8: "..." reachable in the scrolled grid (Users) | Pass | S3-08-users-list-375-start.png, S3-08-users-list-375-scrolled.png | Identifier column visible at scroll 0; "..." fully visible and tappable at max scroll. |
| Item 8: "..." reachable (Delivery Orders) | Pass | S3-08-do-list-375-scrolled.png | "..." is the last column at max scroll, fully visible. |
| Item 8: "..." reachable (Products) | Pass | S3-08-products-list-375-scrolled.png, S3-08-products-list-375-actionscol.png | At *maximum* scroll the actions column had already scrolled past (three more columns - Type, Variant of, Variants - follow it), so the first screenshot shows no "..." button. Scrolling to an intermediate offset shows it fully reachable and tappable. Column *order* is a listing/personalization detail outside S3's scope, not an S3 defect. |

## Ranked failures

1. **Middle-click on a `rowHref` row also navigates the current tab, not just a new one.**
   Entity: Users (list `/user-management/users`), reproduced twice with a clean synthetic
   `auxclick` (`button: 1`) dispatch after wrapping `window.open`. Observed: `window.open(href,
   '_blank', 'noopener,noreferrer')` fires (correct) **and** `window.location.pathname` changes
   to the same detail URL in the current tab (incorrect). Expected per plan 3.2 D5: `onAuxClick
   (middle) -> window.open` only: current tab must stay on the list. This looks like a shared
   click handler that doesn't `return` after the `window.open` branch, so it falls through to
   the `router.push`. Not part of the S3 UAC ids directly (it is S1-06/D5, which S3's rowHref
   reuse depends on), but it affects every `rowHref` list, so flagging here. Not screenshotted
   (a `window.open` call is not visible in a static image); reproduction is the eval script
   output quoted in the table above.
   Fixed by S1 commit 9660d3f44, merged as 43ece00a7.

## Unreachable / not exercised

- **S3-04's true "last page, last row, Next disabled" case** - the dev Users table carries
  several hundred pytest-seeded `*.test.local` rows; walking to the genuine last page (200+
  pages at limit 10) was not practical in this session. See table row above for what was
  verified instead.
- Delivery Orders / Products S3-04 boundary walk (Previous-disabled-at-row-1,
  Next-disabled-at-last-row) was not separately re-driven to exhaustion; only the "walks forward
  one page-crossing, fetches once, cache reuses on the way back" mechanics were confirmed on
  Delivery Orders (16/50 -> 17/50, zero new list requests), relying on the Users run for full
  boundary coverage since the pager is one shared implementation (`useListPager`/`ListPager`).
- One instance during rapid iteration (Delivery Orders list) showed the `order_status_id` filter
  reset to unset when I chained an Escape + row click, and the list issued a stray
  `.../users?...page=1...` request that returned 401 during a scripted 150-click stress loop on
  the Users pagination "Go to next page" control (unrelated legacy `DataGrid` list pager, not the
  S3 record pager). Neither was cleanly reproduced in isolation; noted for awareness, not filed
  as a ranked failure.

## Browser session

`agent-browser@0.27.0`, session `s3-evidence`, closed cleanly at the end of this run (not
`close --all`).

## Run 2B

Verified against `apple-alignment-acceptance-criteria.md` (S3-01..S3-07, D3-D6, D15) and
`PLAN-apple-alignment.md` 3.3/3.4. Worktree `agent-a4fcc3bb35ba62b83`, FE `:3090`, BE `:8000`.
agent-browser 0.27.0, headless, `--session s3-run2b`. No record was created, saved or deleted;
the one destructive menu opened for inspection (Contacts gear) was closed with Escape, never
confirmed.

**Environment note:** the FE dev server under this worktree was rebuilding constantly
(`[Fast Refresh] rebuilding` in the console, repeated full-app "Loading..." remounts) for most of
this run, consistent with a coder actively editing files in the same worktree concurrently.
Client-side `click`/keyboard navigation (sidebar links, command palette, several list rows)
silently failed to route a large fraction of the time with no console error; `agent-browser open
<url>` (hard navigation) was reliable throughout and was used as the fallback once a module had
been reached at least once via sidebar/row click. Several modules below are marked Unreachable
because click-based navigation never completed even after 2-3 retries; this reads as environment
flakiness, not a product defect, but it means those pages were not exercised this run.

### Result table

| Module | Check | Pass/Fail | Screenshot | Note |
|---|---|---|---|---|
| SCM Proforma Invoices | S3-01 toolbar/Back (filter `placement=not_converted` active) | Pass | run2b-pi-detail-1280.png | Back href carries `page`, `limit`, `placement`. |
| SCM Proforma Invoices | S3-02 order | **Fail** | run2b-pi-detail-1280.png | Reads pager, **primary ("Convert to packing list")**, gear - not pager/gear/primary. |
| SCM Proforma Invoices | gear = secondary + Delete red last | Pass | run2b-pi-gear-1280.png | Edit, Export adjusted PI, Delete invoice (last). |
| SCM Proforma Invoices | S3-07 list "..." parity | **Fail** | - | List has no actions column at all (11 plain columns); gear's 3 items have no list-row equivalent. |
| SCM Purchase Orders | S3-01/S3-02 | Pass | run2b-po-detail-1280.png | Pager (1/25, Prev disabled), primary "Edit", no gear - no secondary/delete actions exist anywhere for POs (list has no actions column either), so an empty gear is correctly omitted, not a violation. |
| SCM Sales Orders | S3-01/S3-02 (query filter active) | Pass | run2b-so-detail-1280.png, run2b-so-detail-375.png | Same pattern as PO: pager, primary Edit, no gear (none needed). 375: wraps cleanly under identity, nothing clipped. |
| Conversation SLA Tracking | S3-01 toolbar/Back | Pass | run2b-slatracking-detail-1280.png | One "Back to conversation SLA", carries page/limit/sort/dir. |
| Conversation SLA Tracking | S3-02 order | **Fail** | run2b-slatracking-detail-1280.png | Reads pager, **Refresh**, gear, **Delete as a separate red button after the gear** - three controls beyond pager, not pager/gear/one-primary; Delete lives outside the gear, contradicting D6 ("Delete in the gear, red, last"). |
| Conversation SLA Tracking | gear contents | Pass (internally) | run2b-slatracking-gear-1280.png | 9 secondary items (Sync assignee..Reopen for retest), correctly excludes Delete since Delete is external. |
| Conversation SLA Tracking | S3-07 list row action | **Fail** | run2b-slatracking-rowmenu-1280.png | Row's single unlabelled icon button is not a menu (click adds nothing to the DOM, no `Sync assignee` etc.) - not the same "..." parity item set as the gear's 9 entries. |
| Certificates | S3-01/S3-02 structure | **Fail** | run2b-certificates-detail-1280.png | No separate toolbar row: breadcrumb sits alone, the record's own name is the page H1, and pager/Back/gear are all in one row together - Back is not on a toolbar row of its own, and there is no primary button (Edit lives inside the gear instead). Page reads as not migrated to the shared `DetailActions` pattern. |
| Certificates | gear order | Pass (internally) | run2b-certificates-gear-1280.png | Edit, Merge as revision of, Delete (red, last). |
| Certificates | S3-07 list row action | **Fail** | - | List row's only affordance is a chevron (row-click cue), no "..." menu; gear's 3 items have no list equivalent. |
| Contacts (highest risk) | S3-01 toolbar/Back | Pass | run2b-contacts-detail-1280.png | "Contact Details" H1 + breadcrumb left, one "Back to contacts" right, carries page/limit/sort/dir. |
| Contacts | S3-02 order (moved off toolbar into record card) | Pass | run2b-contacts-detail-1280.png | Identity (avatar+phone+name) left; pager (1/50), gear, primary ("Portal link") right, in that order - matches D6 exactly. |
| Contacts | gear | Pass | run2b-contacts-gear-1280.png | "Delete contact" only, red. |
| Contacts | S3-02 at 375, wraps under identity | Pass | run2b-contacts-detail-375.png | Pager/gear/Portal link drop to their own row below identity block, nothing clipped. |
| Contacts | S3-07 list row action | **Fail** | run2b-contacts-list-375-scrolled.png | List's trailing columns are a "Portal link" icon button and an "Outbound" toggle - no "..." menu, so the gear's "Delete contact" has no list-row equivalent; scrolled to the end at 375 confirms there is nothing further right to reach. |
| Contacts | 375 DataGrid scroll, Phone Number pinned | Pass | run2b-contacts-list-375-start.png | Matches D10. |
| Loading Plan (highest risk) | detail page loads | **Fail (blocking)** | run2b-loadingplan-detail-1280.png, run2b-loadingplan-detail-375.png | Opening the one seeded plan (`/scm/loading-plan/<id>`) renders "Internal server error"; reproduced twice. Network: `POST /api/v1/scm/container-requests/build?include_lines=true` returns 500. All S3-01/S3-02 checks on `LoadingPlanView` are blocked by this. The error state itself does show one "Back to loading plans" link (S3-01 shape intact even in the failure). |
| Loading Plan | list page | Pass | run2b-loadingplan-list-375.png | List loads fine (1 row); 375 list renders without clipping. |
| Integration Logs | S3-01/S3-02 (named exception page) | **Fail** | run2b-integrationlogs-detail-1280.png | Pager ("1/50") still sits in the toolbar row next to "Back", not moved into a record-card row; there is no gear and no primary button at all (a read-only log, so nothing to act on may be legitimate, but the pager placement itself does not match the D6 pattern the other four listed pages now use). |
| Products (Catalogue) | D15 icon buttons -> "..." | Pass | run2b-products-list-1280.png | Row's trailing column holds one "product actions" button only; no separate Edit/Duplicate icon buttons. |
| Stock | pager is presentational, no row click | Pass | run2b-stock-list-1280.png | Rows carry no cursor-pointer/onclick; DataGrid pagination only, consistent with brief. |
| Product Sets | list loads | Pass | run2b-productsets-list-1280.png | 50 rows render fine. |
| Product Sets | detail | Unreachable | - | Row click did not navigate across 2 attempts (env nav flakiness, see note above). |
| Warehouses | detail | Unreachable | run2b-warehouses-detail-1280.png (list only) | Row click (`onclick`, `cursor:pointer` in the a11y tree) never routed across 2 attempts including a real CDP `click`. |
| Onboarding Requests | detail / row action | Unreachable | - | Row has no click handler and no href; two trailing blank-header columns render no visible button in this data set. No detail route found; likely out of S3 scope (list-only, lightbox-driven elsewhere) but not confirmed. |
| Project Sales: Sales Orders, POs, Quotation Documents, Delivery Schedules | N/A | Unreachable (no data) | tmp-projso.png(not saved), tmp-quot.png(not saved) | The dev DB has exactly one project (PRJ-000004, "Registered" stage): 0 sales orders, "Nothing quoted yet", POs/Delivery schedules tabs not reached but same project has nothing drafted at this stage. No record exists to open a detail page against. |
| Project Sales: Series | list | Pass | - | 1 row (Sanitaryware template) renders. |
| Project Sales: Series | detail | Unreachable | - | Row click did not navigate across 3 attempts (eval click, ref click x2). |
| Certificates / SLA gear | Escape closes without acting | Pass | - | Verified for Certificates and Conversation SLA Tracking gears; no destructive action fired. |
| 5 edit forms (Customer, Product, Supplier, Promotion, Complaint) | pager keeps edit mode | Not exercised | - | Not reached this run; time was spent on the higher-priority Contacts/Loading Plan/SCM set and recovering from the navigation flakiness above. |

### Ranked failures

1. **Loading Plan detail 500s** (blocking, highest risk item). `GET /scm/loading-plan/<id>`
   renders "Internal server error"; `POST /api/v1/scm/container-requests/build?include_lines=true`
   returns 500. Reproduced twice, backend otherwise healthy (`:8000/docs` = 200). Blocks all S3
   verification on `LoadingPlanView`, one of the five pages the plan explicitly calls out as
   needing to match the new record-card pattern.
   Environment, not S3: the dev DB lacks `priority_policy.cross_group_borrow_max_qty` (the
   main checkout's model is ahead of the shared database).
2. **Record-card action order wrong on Proforma Invoices**: pager, primary, gear - should be
   pager, gear, primary per D6.
3. **Conversation SLA Tracking record card has three loose controls** (Refresh, gear, a
   standalone red Delete) instead of pager/gear/one-primary; Delete sits outside the gear,
   directly contradicting "Delete in the gear, red, last."
4. **Certificates detail page is not on the shared header/actions pattern**: no distinct toolbar
   row, Back is bundled into the same row as pager and gear, and there is no primary button
   (Edit lives inside the gear).
5. **Integration Logs** (a named "match" target) still has its pager in the toolbar row, unchanged
   from the pre-S3 layout.
6. **S3-07 list/gear parity fails on every SCM/Certificates/SLA/Contacts entity checked except
   Products**: Proforma Invoices, Certificates, Conversation SLA Tracking and Contacts all have a
   gear (or single icon action) with secondary items, but none of their list rows carries the
   equivalent "..." menu with the same items. Products is the one entity where this is done
   correctly.

### Unreachable / not exercised

- Product Sets detail, Warehouses detail, Project Sales Series detail, Onboarding Requests detail:
  click-based row navigation did not complete in this session (see environment note). Not
  re-diagnosed as product bugs given the same daemon's other pages did eventually navigate after
  `open <url>` fallback and the console showed continuous Fast Refresh rebuilds.
- Project Sales Sales Orders / POs / Quotation Documents / Delivery Schedules: no data exists in
  the dev DB to open (single project, "Registered" stage, all four lists empty).
- The five edit-form pager-in-edit-mode checks (Customer, Product, Supplier, Promotion,
  Complaint edit): not reached this run.
- Stock, Warehouses, Product Sets, Onboarding Requests: only the list level was verified; no
  detail-header checks beyond what's in the table.

### Browser session

`agent-browser@0.27.0`, session `s3-run2b`, closed cleanly at the end of this run (not
`close --all`).

## Run 2A

Verified against `apple-alignment-acceptance-criteria.md` (S3-01..S3-07, D3-D6, D15) and
`PLAN-apple-alignment.md` 3.3/3.4. Worktree `agent-a4fcc3bb35ba62b83`, FE `:3090`, BE `:8000`.
agent-browser 0.27.0, headless, `--session s3-run2a`. No record was created, saved or deleted;
every Delete/Trash menu opened for inspection was closed with Escape, never confirmed.

**Environment note:** same as Run 2B - the FE dev server rebuilt constantly
(`[Fast Refresh] rebuilding`, some cycles 20-80s) for the whole run, consistent with a coder
editing files in the same worktree concurrently. A `click` on a sidebar link or list row
routinely returned before the SPA navigation landed; `get url` immediately after a click read
stale in roughly half of all navigations, resolving correctly 2-6s later or on a second `click`.
Two modules (Forms, Access Agents) were retried 2-3x each **and** confirmed via
`network requests --filter` showing zero detail-route fetch even after the retries - those two
are recorded as product findings, not environment noise, on that stronger evidence.

### Result table

| Module | Check | Pass/Fail | Screenshot | Note |
|---|---|---|---|---|
| Complaints | S3-01 toolbar/Back (search `CMP2026` active) | Pass | run2a-complaints-toolbar-1280.png | Toolbar = crumbs + one "Back to complaints" only; href carries page/limit/sort/dir/query. |
| Complaints | S3-02 order | **Fail** | run2a-complaints-toolbar-1280.png | Reads pager, **primary** ("Edit technical team response"), Download PDF, print count, **gear last** - not pager/gear/primary. Complaints is one of the plan's named "workflow menu, moved unchanged" exceptions, but the exception covers the gear's *contents*, not this ordering; flagging per D6. |
| Complaints | gear = secondary + Delete red last | Pass | run2a-complaints-gear-1280.png | "Complaint actions": Escalate SLA..Update & Reply, then Void (red), Delete (red, last). |
| Complaints | S3-07 list row action | Unreachable | - | Grid has no "..." row menu at all (only a print-count icon); gear's ~10 items have no list-row equivalent to compare against. |
| Complaints | S3-02 at 375, wraps under identity | Pass | run2a-complaints-detail-375.png | Pager row, then primary, then Download PDF/print/gear drop to their own rows; nothing clipped. |
| Complaints | S3-03/S3-04 Next fires no list request | Pass | - | Network log: `.../complaints-management/complaints?...` fetched once before and after Next; URL id changed (CMP2026-0032 -> -0031), no new list GET. |
| Customers | S3-01/S3-02/S3-07 | Pass | run2a-customers-toolbar-1280.png, run2a-customers-gear-1280.png | Toolbar = crumbs + Back only; card = pager (1/1), gear, primary "Edit" in order; gear = "Delete customer" red; row's "..." menu is identical single item - full match to D6/D15. |
| Suppliers | S3-01/S3-02/S3-07 | Pass | run2a-suppliers-toolbar-1280.png, run2a-suppliers-gear-1280.png, run2a-suppliers-rowmenu-1280.png | Same clean pattern as Customers; Back href carries query; row "..." = gear exactly. |
| GRN (highest risk) | S3-01/S3-02 order | Pass | run2a-grn-toolbar-1280.png | Toolbar = crumbs + Back only; card = pager (1/1), gear, primary "Edit", in order. |
| GRN | gear "no longer lists the current status" | Confirmed, not a defect | run2a-grn-gear-1280.png | Gear = "Mark as Draft", "Mark as Rejected", separator, "Delete GRN" red last - the current status ("Approved") is correctly excluded from a switch-to menu (can't mark it as what it already is) and remains visible via the badge next to the title. Functionally intact; flagged per the brief for the captain's call on whether the old menu's radio-style "see current status here too" UX is a requirement. |
| GRN | S3-07 list row parity | Pass | run2a-grn-rowmenu-1280.png | Row "GRN actions" = identical 4 items/order to the gear. |
| GRN | 375: wraps, "..." reachable scrolled | Pass | run2a-grn-detail-375.png, run2a-grn-list-375-scrolled.png | Detail card wraps cleanly; list "..." fully visible and tappable at max horizontal scroll. Note (out of S3 scope, S1-05/D10): at max scroll the identifier ("GRN Number") column is not visibly pinned - only a sliver of the next column shows at the left edge - worth a separate look under S1/S4, not scored here. |
| Promotions | S3-01/S3-02/S3-07 | Pass | run2a-promotions-toolbar-1280.png, run2a-promotions-gear-1280.png, run2a-promotions-rowmenu-1280.png | Card = pager (1/1), gear, primary "Edit" in order; gear = row menu = "Delete promotion" only, red. First attempt read as a row-click bug (no navigation, no dialog) but a retry + longer wait landed correctly - environment flakiness, not a defect; see note above. |
| Forms | S3-07 row action / row click | **Fail** | run2a-forms-rowmenu-1280.png | Row click fires no navigation (confirmed via `network requests` - zero fetch to a `/forms-management/forms/<id>` route across 2 clicks incl. a `find text click`); row's only menu item is "Delete form", no Edit/View. There is no way to open a Form's detail/edit view from this list at all. S3-01/S3-02 unreachable as a result. |
| Stock Transfers | S3-01 toolbar/Back | Pass | run2a-stocktransfers-toolbar-1280.png | Crumbs + one "Back to transfers"; href carries page/limit/sort/dir/query. |
| Stock Transfers | S3-02 order | **Fail** | run2a-stocktransfers-toolbar-1280.png | Reads pager, **primary** ("Approve"), **gear last** ("More actions") - not pager/gear/primary, and Stock Transfers is **not** one of the plan's named workflow-menu exceptions, so this is a plain D6 violation. |
| Stock Transfers | gear vs row-menu parity | Note | run2a-stocktransfers-gear-1280.png, run2a-stocktransfers-rowmenu-1280.png | Gear = "Cancel" only, not styled red. Row menu = "Approve" + "Cancel", with **Cancel styled red** there. Same two actions, different set (row menu also offers Approve) and different Cancel colour - a parity/consistency gap alongside the ordering one. |
| Sales Agents | S3-01/S3-02, single-row 1/1 | Pass | run2a-salesagents-toolbar-1280.png | Filtered to one row ("ACT"): pager reads "1 / 1" with **both chevrons visibly disabled**; card = pager, primary "Edit" (no gear - correctly omitted, nothing secondary/destructive is offered for this entity anywhere in the UI). |
| Access Agents ("AI Agents" in the current sidebar/page copy; route `/user-management/access-agents`) | S3-07 row action / row click | **Fail** | run2a-accessagents-rowmenu-1280.png | Same defect as Forms: row click fires no navigation (confirmed via `network requests`, zero detail fetch across 2 clicks); row's only menu item is "Delete access agent", no Edit/View path exists. |
| Attachments (modal stepper) | pager mechanics | Pass | run2a-attachments-modal-1280.png, run2a-attachments-stepper-next-1280.png | Row click opens an in-place modal ("1 / 50"); Next advances the counter to "2 / 50" in place (URL unchanged, `attachments/drive` list endpoint fetched exactly once, no re-fetch on Next). Action row (Preview, Download, Resubmit, red "Move to Trash") is a flat button strip, not a gear - this is D8 lightbox territory, not the D6 detail-page pattern, so not scored against pager/gear/primary. |
| Packing Lists (highest risk) | S3-01/S3-02 order | Pass | run2a-packinglists-toolbar-1280.png | Toolbar row = title/eyebrow/crumbs + one "Back to packing lists" only, nothing else - pager/gear/primary correctly **moved off the toolbar** into their own row in the record card, reading pager (1/1), gear, primary "Download packing list", in that exact order. |
| Packing Lists | gear = secondary + Delete red last | Pass | run2a-packinglists-gear-1280.png | Edit, Import Container Status workbook, separator, Delete (red, last) - clean D6 match. |
| Packing Lists | 375: wraps, "..." reachable scrolled | Pass | run2a-packinglists-detail-375.png, run2a-packinglists-list-375-scrolled.png | Detail: pager+gear on one row, primary drops to its own full-width row below, nothing clipped. List: "..." fully visible and tappable at max scroll. |
| Purchase Requests | S3-01/S3-02 (named exception) | Pass (exception pattern) | run2a-purchaserequests-toolbar-1280.png | Toolbar = crumbs + Back only. Card: pager, "Processed by CS" workflow-status button, gear, print count, Edit, **Delete as a separate red standalone button, last** - flat multi-button "workflow menu, moved unchanged" layout per the brief's exception; Delete is still last and red, satisfying D6's core promise even without a literal single gear. |
| Purchase Requests | gear contents | Pass | run2a-purchaserequests-gear-1280.png | 9 secondary items ending in "Void" (red); Delete lives outside the gear as its own button, consistent with the flat layout above. |
| Stock Inquiries | S3-01/S3-02 (named exception) | Pass (exception pattern) | run2a-stockinquiries-toolbar-1280.png | Toolbar = crumbs + Back only. Card: pager, "Approve (send to purchasing)" (blue), "Reject" (red outline), print count, gear last - same flat workflow-menu pattern as Purchase Requests/Complaints. |
| Stock Inquiries | gear = secondary + Void/Delete red last | Pass | run2a-stockinquiries-gear-1280.png | Edit..Export to Excel, then Void (red), Delete (red, last). |
| Sponsorship Forms (reachable, lightly exercised) | S3-01 toolbar/Back | **Fail** | run2a-sponsorshipforms-toolbar-1280.png | No "Back to sponsorship forms" (or any Back) control exists anywhere on the page - confirmed absent via full-page snapshot grep, not just off-screen. Breadcrumb is present and correct ("Home > Project Sales Admin > Sponsorship Forms > Details"); only the mandated Back button is missing. Title also wraps to two lines at 1280, pushing "Edit"/"Delete" onto a second row even at desktop width - a possible secondary wrap issue, not separately scored here given time. |

### Ranked failures

1. **Forms and Access Agents have no way to open a record at all.** Row click fires zero
   navigation (confirmed by network log, not just a slow click) and the row's "..." menu offers
   only Delete - no Edit, no View. This is a stronger break than "row click is broken cosmetically":
   there is currently no UI path to see or edit a Form or an Access Agent's fields once created.
2. **Sponsorship Forms detail page has no Back button.** S3-01 requires exactly one "Back to
   [list]"; this page has none, confirmed by grepping the full accessibility tree, not a viewport
   crop.
3. **Stock Transfers record-card order is pager, primary, gear** - the plain, un-exempted D6
   violation (Complaints/PR/Stock Inquiries at least have the "moved unchanged" carve-out; Stock
   Transfers does not).
4. **Stock Transfers gear/row-menu are not the same set**: the detail gear offers only "Cancel"
   (uncoloured); the list row's menu offers "Approve" + "Cancel", with Cancel styled red there and
   plain on the detail page - both a D15 parity gap and a colour-consistency gap on the same action.
5. **Complaints record-card order is also pager, primary, [extra buttons], gear-last** - inside the
   named exception for gear *contents*, but the left-to-right slot order still doesn't read
   pager/gear/primary as D6 specifies.

### Unreachable / not exercised

- Complaints' S3-07 list "..." parity: the list has no row-level menu to compare against the
  gear's ~10 items (structural, not a navigation failure).
- Sponsorship Forms: only S3-01 was checked given the time already spent recovering from
  navigation flakiness across the run; gear contents and row-menu parity were not verified.
- The GRN pinned-identifier-column observation at 375 is S1-05/D10 territory, out of S3's scope;
  noted for awareness only, not scored.

### Browser session

`agent-browser@0.27.0`, session `s3-run2a`, closed cleanly at the end of this run (not
`close --all`).

## Run 3A

Re-sweep after the fix round, against `apple-alignment-acceptance-criteria.md` (S3-01..S3-07, D6,
D15) and the Run 2A findings it targets. Worktree `agent-a4fcc3bb35ba62b83`, FE `:3090`, BE
`:8000`, agent-browser 0.27.0, headless, `--session s3-run3a`. No record created, saved or
deleted. Environment note: the FE dev server rebuilt via Fast Refresh repeatedly through the run
(cycles up to ~50s), so a click's effect frequently only appeared after a retry + wait; every
"unreachable" claim below was re-confirmed via `network requests` (a real absent detail fetch),
not just a slow `get url`.

### Result table

| Module | Check | Pass/Fail | Screenshot | Note |
|---|---|---|---|---|
| Complaints | S3-01 Back restores filter | Pass | run3a-complaints-back-liststate-1280.png | Back to complaints returns with `query=CMP2026` intact (B2 fix confirmed). |
| Complaints | S3-02 order | **Still Fail** | run3a-complaints-toolbar-1280.png | Reads pager, primary (Download PDF), print count, **gear last** - unchanged from Run 2A. |
| Complaints | gear contents | Pass | run3a-complaints-gear-1280.png | Secondary items, then Void/Delete red, Delete last. |
| Complaints | row "..." parity | Unreachable (structural) | run3a-complaints-rowmenu-1280.png | List still has no row action menu, only a print-count icon; unchanged from Run 2A. |
| Complaints | 375 wrap | Pass | run3a-complaints-detail-375.png | Wraps cleanly under identity, nothing clips. |
| Stock Transfers | S3-02 order | **Fixed** | run3a-stocktransfers-toolbar-1280.png | Now pager, gear only (no primary shown - correct, nothing to do on an Approved transfer). |
| Stock Transfers | gear vs row parity | **Fixed** | run3a-stocktransfers-gear-1280.png, run3a-stocktransfers-rowmenu-1280.png | Both = "Cancel transfer", red, identical. |
| Stock Transfers | 375 wrap | Pass | run3a-stocktransfers-detail-375.png | Clean wrap. |
| Forms | row navigation | **Improved, partial** | run3a-forms-toolbar-1280.png, run3a-forms-rowmenu-1280.png | Detail page now reachable via the Form Code cell (now a real link) and shows correct pager/gear/Edit order + single Back. Clicking elsewhere on the row still does not navigate (confirmed via network log, zero new fetch) - inconsistent with modules where the whole row is clickable. |
| Access Agents | row navigation | **Improved, partial** | run3a-accessagents-toolbar-1280.png | Same pattern as Forms: Code-cell link works, whole-row click does not. Detail order pager/gear/Edit correct, single Back. |
| Sponsorship Forms | S3-01 Back | **Fixed** | run3a-sponsorshipforms-toolbar-1280.png | "Back to sponsorship forms" present, restores `request_type` filter. Card keeps the flat workflow-menu exception pattern (pager, status CTA, gear, Edit, Delete standalone red last). |
| Customers | Back restores status filter | Pass | run3a-customers-back-liststate-1280.png | Back returns with Filters badge "1" (Active) intact; detail order pager/gear/Edit correct. |
| Suppliers | order/Back | Pass, no regression | run3a-suppliers-toolbar-1280.png | pager/gear/Edit, single Back. |
| GRN | order/Back | Pass, no regression | run3a-grn-toolbar-1280.png | pager/gear/Edit, single Back. |
| Promotions | detail pattern | Not comparable | run3a-promotions-lightbox-1280.png | Opens an attachments-style lightbox (Preview/Download/Resubmit/Move to Trash-red), not a `DetailActions` page - D8 territory per the Run 2A precedent for the Attachments stepper, not scored against pager/gear/primary. |
| Purchase Requests | order/Back (exception) | Pass, no regression | run3a-purchaserequests-toolbar-1280.png | Flat workflow-menu layout unchanged; Delete standalone red last. |
| Stock Inquiries | order/Back (exception) | Pass, no regression | - | Same flat pattern, unchanged. |
| Packing Lists | order/Back | Pass, no regression | run3a-packinglists-toolbar-1280.png | pager/gear/primary "Download packing list", single Back. |
| Sales Agents | 1/1 disabled chevrons | Pass, no regression | run3a-salesagents-toolbar-1280.png | Both Previous/Next `disabled` in DOM; no gear (correctly omitted). |

### Ranked findings

1. **Complaints record-card order is still pager, primary, gear-last** - the one Run 2A defect
   this round did not fix. Everything else about Complaints (Back/filter restore, gear contents,
   375 wrap) is now correct.
2. **Forms and Access Agents are reachable again but inconsistently** - the previous "no way to
   open a record at all" is fixed via a new Code-cell link, but a click anywhere else on the row
   still does nothing (confirmed via network log, not just a slow click), unlike every other
   module swept where the whole row navigates. Worth a follow-up to make the row uniformly
   clickable rather than only the one cell.
3. Complaints' list still has no row "..." menu at all (structural, same as Run 2A - the gear's
   items have nothing to compare against on the list).

### Fixed since Run 2A

Stock Transfers order + gear/row parity, Sponsorship Forms Back button, Customers Back-restores-
status-filter (B2), Complaints Back-restores-query, Forms/Access Agents detail reachability
(partially).

### Unreachable / not exercised

- Promotions' underlying `DetailActions` page (if one still exists) was not reached - the row
  action opens the attachments lightbox by default; not re-diagnosed further given time budget.
- Rows-per-page combobox exercise was skipped for most modules after the Complaints attempt did
  not fire a request reliably; search/filter was used as the primary list-state check instead.

### Browser session

`agent-browser@0.27.0`, session `s3-run3a`, closed cleanly at the end of this run (not
`close --all`).

## Run 3B

Verified against `apple-alignment-acceptance-criteria.md` (S3-01..S3-07, D6, D15). Worktree
`agent-a4fcc3bb35ba62b83`, FE `:3090`, BE `:8000`, agent-browser 0.27.0 headless, session
`s3-run3b`. No record created, saved or deleted; Delete/Trash dialogs opened for inspection were
closed with Cancel or Escape.

**Environment note:** the FE dev server rebuilt continuously through the whole run (Fast Refresh
cycles from 2s to 52s, one 52512ms), consistent with concurrent coder activity in the same
worktree. Nearly every list-row and sidebar-link click needed a retry plus an 8-15s wait before
the URL actually changed; `get url` read stale dozens of times. Findings below are only recorded
as Fail after 2+ reproductions with fresh refs and full waits.

### Result table

| Module | Check | Pass/Fail | Screenshot | Note |
|---|---|---|---|---|
| Conversation SLA Tracking | toolbar/order (was: loose Refresh + standalone Delete) | **Fixed - Pass** | run3b-slatracking-detail-1280.png | Toolbar = crumbs + one Back only, href carries query=60. Card = pager (2/30), gear only (no primary, correctly none exists); Refresh now lives inside the gear, Delete tracking is red and last. |
| Conversation SLA Tracking | S3-07 row "..." parity | **Fail** | run3b-slatracking-rowmenu-1280.png | Row menu opens (progress from Run 2B's "not a menu at all") but shows only 1 item ("Sync assignee") vs. the gear's 8 items - truncated/clipped list, not full parity. |
| Certificates | toolbar/order (was: unconverted) | **Fixed - Pass** | run3b-certificates-detail-1280.png | Now on the shared pattern: distinct toolbar row (crumbs + one Back), record-card row = pager (2/9), gear, primary "Edit", in order. Gear = "Merge as revision of...", separator, "Delete certificate" red last. |
| Certificates | 375, group wraps | Pass | run3b-certificates-detail-375.png | Pager/gear/Edit drop to their own row under the title block; nothing clipped. |
| Certificates | S3-07 row "..." parity | Not verified | run3b-certificates-rowmenu-1280.png | Row now has a "certificate actions" menu (was chevron-only in Run 2B) but the actions column sits past the DataGrid's horizontal scroll edge at 1280 and time did not allow scrolling the grid to open it; not scored. |
| Integration Logs | pager placement (was: pager on toolbar) | **Fixed - Pass** | run3b-integrationlogs-toolbar-1280.png | Toolbar now holds only crumbs + one "Back to integration logs"; pager (2/50) sits in its own row below, matching the five-page exception list. No gear/primary, correctly - a read-only log has nothing to act on; no row menu on the list either, consistent. |
| Proforma Invoices | record-card order (was: pager, primary, gear) | **Fixed - Pass** | run3b-pi-detail-1280.png, run3b-pi-gear-1280.png | Card now reads pager (2/6), gear only - no primary shown (this revision is Superseded/Not converted, so nothing to Edit). Gear = "Export adjusted PI", separator, "Delete invoice" red last. Back restores `placement=not_converted`. |
| SCM Sales Orders | record-card order | Pass | run3b-so-detail-1280.png | Toolbar = crumbs + one Back; card = pager (2/25), primary "Edit", no gear. List row carries an inline "Delete" button (not a gear/menu) not reachable from the detail page - an asymmetry, not a hard fail per the brief's no-secondary-action carve-out, but worth a follow-up look. |
| SCM Purchase Orders | record-card order | Pass | run3b-po-detail-1280.png | Same shape as Sales Orders: toolbar clean, card = pager (2/25), primary "Edit", no gear. |
| Products (list + detail) | no Edit/Duplicate icons, row "..." + gear | Pass | run3b-products-list-1280.png, run3b-products-detail-1280.png | List row shows one "product actions" control only. Detail: toolbar clean, card = pager (2/50), gear, primary "Edit" in order; gear = "Delete product" only, red. |
| Project Sales > Series | toolbar/order (was: unconverted) | **Still Fail** | run3b-series-detail-1280.png | Opens straight into an always-editable form (Name/Brand/Categories/Description + Cancel/Save changes); toolbar is correct (crumbs + one Back) but there is no pager, no gear, no primary anywhere on the page - not on the shared pattern. Only 1 record exists so a pager may be legitimately hideable, but Run 2B's "unconverted" finding stands unchanged. |
| Onboarding Requests | reachability + toolbar (was: unreachable) | **Reachable now, new Fail** | run3b-onboarding-detail-1280.png | Row click now navigates (was completely unreachable in Run 2B). But pager, gear ("Request actions"), and the "Back to onboarding requests" link all sit in the SAME row - no separate toolbar row for Back alone, replicating Certificates' old (now-fixed) defect. Gear itself is clean: Copy link, Revoke link, Issue a new link, separator, Delete red last. |
| Users (Administrative Users) | toolbar/order + delete dialog | Pass | run3b-users-deletedialog-1280.png | Card = pager (2/10), gear, primary "Edit user". Gear = Impersonate user, Send invitation link, separator, Trash user (red) - matches the AC's named example exactly. "Trash user" opens a proper `AlertDialog` requiring the user's email typed to confirm, pager/gear/Edit still visible dimmed behind it; Cancel closed it with no request fired. |
| Customer edit (pager in edit mode) | Next keeps you in edit mode | **Fail** | run3b-customer-edit-mode-1280.png, run3b-customer-edit-afternext-1280.png | Edit is a dedicated `/customers/{id}/edit` route, not an inline toggle - already a deviation from "View and Edit are the SAME layout." Clicking Next while editing did not advance to the next customer AND did not stay in edit mode: it landed back on the View page for the SAME record (still "2/50"), discarding the edit context. |
| Warehouses | detail reachability | **Fail, reproduced 4x** | - | Row `click`, `find text`, and a second fresh-ref `click` all failed to navigate across 4 attempts with full waits; same as Run 2B's "Unreachable," now confirmed reproducible rather than environment noise. |
| Product Sets | detail reachability | **Fail, reproduced 2x** | - | Same as Warehouses - row click never routed across 2 fresh attempts. Same as Run 2B. |
| "Contacts" (Respond.io Contacts, System > Messaging) | detail reachability | **Fail, reproduced 4x** | run3b-tmp-contacts2.png (list only) | Could not locate a dedicated "Contacts" listing anywhere in the sidebar under that name; the in-app search maps "contacts" only to this page. Rows are plain `row [onclick]` (no `<a>`/link), and clicking never routed across 4 attempts (2 different rows, 1 `find text`) despite 5-12s waits each. If this is not the module the plan means, the actual "Contacts" route was not found this run - flagging as a discovery gap either way. |
| Attachments (modal stepper) | not exercised | Not exercised | - | Time budget ran out after 3 navigation attempts to Resources > Files stalled on the same Fast-Refresh lag; not reached. |

### Ranked failures

1. **Customer edit: Next during edit mode neither advances the record nor stays in edit mode** -
   it silently drops back to View on the same record. Directly contradicts the checked behaviour
   ("the pager keeps you in edit mode").
2. **Onboarding Requests, now reachable, has pager + gear + Back all crammed into one row** - the
   exact defect Certificates just had fixed; Back is not alone in its own toolbar row.
3. **Project Sales > Series remains fully unconverted** - no pager, no gear, no primary; unchanged
   since Run 2B.
4. **Conversation SLA Tracking's row "..." menu shows 1 of 8 gear items** - a menu now exists
   (progress) but S3-07 parity is still broken, just differently than Run 2B's "not a menu" finding.
5. **Warehouses and Product Sets detail are confirmed unreachable**, not environment flakiness -
   reproduced 4x and 2x respectively with fresh refs and long waits.
6. **"Contacts" could not be located/opened at all this run** - either a genuine reachability bug
   on Respond.io Contacts (the closest match by content shape) or the intended module was never
   found; needs the captain to confirm which page S3's "Contacts" module refers to.

### Fixed since Run 2B (confirmed this run)

Certificates (full toolbar/card conversion), Integration Logs (pager off the toolbar row),
Proforma Invoices (pager/gear/primary order), Conversation SLA Tracking (Refresh into the gear,
Delete no longer standalone), and the Back-link-restores-list-state fix (query, filter, sort all
round-tripped correctly on SLA Tracking, Integration Logs, Proforma Invoices and Certificates).

### Unreachable / not exercised

- Attachments modal stepper: not reached (time).
- Certificates row "..." menu contents: button exists but sits past the 1280px grid's horizontal
  scroll edge; not opened.
- SCM Sales Orders list-row inline Delete vs. detail-page gear absence: noted, not deep-dived.
- 375 check for Contacts: skipped, detail was unreachable so there was nothing to screenshot.

### Browser session

`agent-browser@0.27.0`, session `s3-run3b`, closed cleanly at the end of this run (not
`close --all`).

## Run 3C - the coder's check of runs 3A/3B (round 3)

`agent-browser@0.27.0`, session `s3-coder` on `:3090`, closed by name at the end.

Clicks are dispatched on a named cell rather than the row's geometric centre. A `click @ref` on a
`<tr>` lands on whatever cell happens to be under the middle of a horizontally scrolled grid, which
in these lists is often the checkbox or the actions cell, and both of those are in
`ROW_INTERACTIVE_SELECTOR` and deliberately do NOT open the record. That is what makes a row look
dead when it is not.

| Finding | Verdict | Evidence |
| --- | --- | --- |
| 5. Forms and Access Agents open only from the code link | **Not reproduced.** Clicking an inert cell navigates: `/forms-management/forms/<id>?page=1&limit=50&sort=updated_at&dir=desc` and `/user-management/access-agents/<id>?page=1&limit=50&sort=created_at&dir=desc`. Both grids already passed `rowHref`. A client-side route change writes no network entry, which is what the network log was reading. | URLs above |
| 9. Warehouses and Product Sets never route | **Reproduced and fixed.** Neither grid passed `rowHref` at all; warehouses had a chevron button at the end of the row and product sets a link on one cell. Both now navigate from any inert cell, carrying the list query. | run3c-warehouses-rowclick-detail-1280.png |
| 10. Promotions row click opens an attachments lightbox | **Not a row-click defect.** Every cell of a promotion row opens the promotion; the Attachments cell also holds a 14px "View details of <file>" eye button inside a 537px cell (2.6% of its width), and that button opens the flyer lightbox, which is its job. Marketing > Promotions also has a separate **Promotion Attachments** list whose rows ARE attachments. Nothing changed here. | run3c-promotions-attachment-eye-1280.png |
| 4. Onboarding row shows only a chevron | **Fixed.** The row's "..." now reads Revoke link, Issue a new link, Delete - the record's gear minus Copy link, whose intake URL the list payload does not carry (it is a credential). | run3c-onboarding-rowmenu-1280.png |

## Run 4 - targeted re-check after round 3 fixes

`agent-browser@0.27.0`, session `s3-run4` on `:3090`, closed by name at the end. No record
created, saved or deleted. Environment note: the FE dev server rebuilt continuously through the
run (Fast Refresh cycles seen up to 34s), and most grids are wider than the 1280px viewport, so a
`click @ref` on a row link often lands off-screen and silently no-ops; every navigation below was
confirmed via `network requests` or a fresh `snapshot`, not a single `get url` read, and several
needed a manual `scrollIntoView({inline:'center'})` on the target cell before the click landed.

### Result table

| Module | Check | Pass/Fail | Screenshot | Note |
|---|---|---|---|---|
| Complaints | 1. D6 order | Pass | run4-complaints-gear-1280.png | Toolbar = crumbs + one Back. Card = pager (1/50), gear only, nothing else. Gear = 7 secondary items, separator, Void + Delete both red, Delete last. |
| Stock Inquiries | 1. D6 order | Pass | run4-stockinquiries-gear-1280.png | pager (1/44), gear, primary cluster (Approve/Reject workflow CTA - allowed). Gear separator before Void/Delete red last. |
| Purchase Requests | 1. D6 order | Pass | run4-purchaserequests-gear-1280.png | pager (1/50), gear, primary cluster (Change to pending approval/Reject/Edit). Gear separator before Void/Delete red last. |
| Onboarding Requests | 1. D6 order (ToolbarActions = Back only) | Pass | run4-onboarding-gear-1280.png | Toolbar has only "Back to onboarding requests", nothing else. Card = pager (5/9), gear, primary (Start review). Gear separator before Delete red last (Revoke link/Issue a new link disabled while link is active - correct). |
| Series (Project Sales) | 1. D6 order | Pass, improved | run4-series-gear-1280.png | Was "Still Fail" in Run 3B (no pager/gear/primary at all). Now: toolbar = crumbs + Back only; action row = gear alone (no pager - only 1 series row exists, acceptable; no primary - form uses its own inline Save/Cancel). Gear = single "Delete series", red. |
| Conversation SLA Tracking | 1. D6 order | **Fail (new)** | run4-slatracking-gear-1280.png | pager (1/31) + gear order is correct and no primary shown (correct, nothing to edit inline). But inside the gear "Delete tracking" is red yet NOT last - Portal link, Escalate, Overwrite assignee, Set current tier started at, Set initiated at, Mark as responded, Mark as resolved, Reopen for retest all sit below it. Violates "separator, then Delete last". |
| Leads | 1. D6 order + S3-01 Back | **Fail (new)** | run4-leads-gear-1280.png | No "Back to leads" button anywhere in the toolbar (only the breadcrumb "Leads" link, which is a plain crumb, not a labelled Back button) - S3-01 violation. No pager either. Gear present with one item ("Delete lead", red). |
| Project detail | 1. D6 order + S3-01 Back | **Fail (new)** | run4-project-gear-1280.png | Same missing-Back defect as Leads (breadcrumb only, no "Back to..." button). No pager. Order is reversed: primary ("Spec in") sits BEFORE the gear, not after - should read gear then primary. Gear itself is fine internally: Back to identified/PO received/Mark lost/Mark dormant, separator, Delete project red last. |
| Onboarding Requests | 2. D15 row "..." parity | Pass | run4-onboarding-rowmenu-1280.png | Row = Revoke link, Issue a new link, Delete - exactly the gear's order minus Copy link (intake URL not in the list payload, documented exclusion from Run 3C). |
| Conversation SLA Tracking | 2. D15 row "..." parity | Fail (unchanged) | run4-slatracking-rowmenu-1280.png | Row = Sync assignee, Delete tracking only (2 of the gear's 10 items). Page-bound items (Portal link, Escalate, tier timestamps, Mark as responded/resolved, Reopen) are correctly gear-only, so the gap itself is expected per the brief, but see the Delete-not-last defect above - it affects the gear both places would need to match against. |
| Attachments (Resources > Files) | 2. D15 row "..." parity | Not comparable (structural) | - | Files have no route/gear/pager at all; clicking a row opens a modal ("2026-7-27 库存明细.xlsx", pager 1/50 inside the modal) with Preview / Download / Resubmit / Move to Trash as plain buttons, not a dropdown. No Rename affordance found anywhere in the modal. Different pattern from the shared `DetailActions`, unchanged since earlier rounds. |
| SCM Sales Orders | 2. D15 row "..." parity | Pass | run4-so-rowmenu-1280.png, run4-so-gear-1280.png | Both = "Delete" only, red. Detail card = pager (1/25), gear, primary (Edit). |
| Complaints | 2. D15 row "..." parity | Fail (structural, unchanged) | - | List still has no "..." menu - only a print-count "0" button per row. Nothing to compare the gear against. |
| Forms | 3. Whole-row click | Pass | - | Clicking the description cell (after scrolling it into view - the grid is 2314px wide vs 1280 viewport) routes to `/forms-management/forms/<id>?...`. |
| Access Agents | 3. Whole-row click | Pass | - | Clicking the "Active" status cell routes to `/user-management/access-agents/<id>?...`. Sidebar entry is labelled "AI Agents" but the route is `access-agents`. |
| Warehouses | 3. Whole-row click | Pass | - | Clicking a cell below the fold (after `scroll down 800`) routes to `/inventory-management/warehouses/<id>?...`. |
| Product Sets | 3. Whole-row click | Pass | - | Clicking the description cell routes to `/master-data-management/product-sets/<id>?...`. |
| Promotions | 3. Whole-row click | Pass | - | Clicking the Start Date cell routes to `/marketing-management/promotions/<id>?...`; confirms Run 3C's finding that only the small in-cell "eye" icon on the Attachments column opens the flyer lightbox instead. |
| Customer edit | 4. Next during edit | **Fail (unchanged)** | run4-customeredit-afternext-1280.png | From `/customers/{id}/edit` (pager showed "1 / 50"), clicking Next did not advance to the next customer's edit screen. It landed on the View page for the SAME customer (`{id}` unchanged, no `/edit` suffix, pager still "1 / 50"), silently dropping edit mode. Matches Run 3B's finding exactly - not fixed this round. |
| Users | 5. Back single fetch | Pass (better than spec) | run4-users-back-liststate-1280.png | Set search "Jayson" + rows-per-page 10 (search needed an explicit Enter - `fill()` alone did not trigger the debounced request), opened row 2 (Jayson SK), clicked Back. Zero new requests fired to `/api/v1/user-management/users?...` after Back (served from the existing react-query cache entry) - stricter than "exactly one". List visually restored `query=Jayson`, `limit=10`, showing "1 - 3 of 3". |
| Complaints | 6. 375 wrap | Pass | run4-complaints-detail-375.png | Pager/gear group drops to its own row under the title/status line; nothing clipped. |
| Onboarding Requests | 6. 375 wrap | Pass | run4-onboarding-detail-375.png | Same clean wrap under the identity block. |

### Ranked failures

1. **Customer edit: Next during edit mode still drops back to View on the same record** - unchanged
   since Run 3B. The one most likely to actively mislead a user (silent data-entry loss risk if
   they had typed something first).
2. **Leads and a Project detail have no "Back to..." button at all** - only the plain breadcrumb
   crumb, which is not a labelled Back action and does not match every other module swept (Series,
   Onboarding, Complaints, Stock Inquiries, Purchase Requests, SO all have one). Same root cause
   likely explains the missing pager on both.
3. **Project detail's primary ("Spec in") sits before the gear, not after** - the one D6 order
   defect that is a pure ordering bug rather than a missing element.
4. **Conversation SLA Tracking's gear does not end on Delete** - "Delete tracking" is red but eight
   more items (four of them destructive/mutating: Overwrite assignee, Set current tier started at,
   Set initiated at, Reopen for retest) follow it. New finding this round; Run 3B only flagged the
   row-vs-gear item-count gap, not this internal ordering issue.
5. **Complaints list still has no row "..." menu at all** - structural, unchanged since Run 2A/3A/3C.
6. **Attachments (Resources > Files) remains off the shared `DetailActions`/gear pattern** -
   modal-based with plain buttons (Preview/Download/Resubmit/Move to Trash), no Rename anywhere,
   unchanged since earlier rounds.

### Fixed since Run 3

Series (Project Sales) now has a working gear with Delete, was fully unconverted before. Stock
Inquiries, Purchase Requests, Onboarding Requests, SCM Sales Orders, Complaints (D6 order and 375
wrap; row-menu absence is the one remaining, structural item) all confirmed Pass with no
regression. Forms, Access Agents, Warehouses, Product Sets and Promotions all whole-row-click
correctly - Run 3C's fixes hold. Users list Back is a clean single/zero-fetch restore.

### Unreachable / not exercised

- Loading Plan detail was skipped per the brief (known 500 on this dev DB from a missing column);
  its list view was not separately re-checked this run since it was not in the requested scope.
- Certificates row "..." menu contents (flagged unreached in Run 3B for being past the grid's
  horizontal scroll edge) was not re-attempted; not in this run's module list.

### Browser session

`agent-browser@0.27.0`, session `s3-run4`, closed cleanly at the end of this run (not `close --all`).
