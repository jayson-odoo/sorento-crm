# M4 List latency - browser verification evidence (agent-browser, 2 Sep 2026)

Second attempt after a fix round. Worktree `motion2-M4` (branch `feat/motion2-M4-list-latency`),
FE dev server `PORT=3081 npm run dev` (own session, PID 87342), BE reused read-only on `:8120`
(another lane's). Session `--session m4tester` (isolated browser). Login via `E2E_EMAIL`/
`E2E_PASSWORD` from `.env.local`. Viewport 1280x800 unless noted. Navigated by sidebar/command
palette clicks from `/`, never a deep URL, per policy.

Method for catching a transition that is too fast on localhost to see with the naked eye: an
in-page `window.fetch` patch (or, for the hard-reload column-preference check, a CDP
`--init-script` registered before the reload) added a 500-900ms artificial delay to the grid's own
list endpoint, then a tight polling loop (25-50ms) read `document.querySelector('table')`'s
`[data-slot="skeleton"]` count and the `<tbody>` class list for `opacity-60` for the duration of
the delay. This is the same DOM the AC criteria are written against; the network log
(`network requests --filter`) independently confirms each interaction actually fired the request
it claims to.

## Findings summary (pass/fail table)

| Check | Grid | Result | Observation |
| --- | --- | --- | --- |
| M4-02 Next | Products | **FAIL (dim)**, pass (skeleton) | maxSkeleton 0, `opacity-60` never observed over 1.5s |
| M4-02 Prev | Products | **FAIL (dim)**, pass (skeleton) | maxSkeleton 0, no dim; pagination strip stayed present/enabled |
| M4-02 Sort (Product Code) | Products | **FAIL (dim)**, pass (skeleton) | maxSkeleton 0, no dim |
| M4-02 Filter (Status=Active) | Products | **FAIL (dim)**, pass (skeleton) | maxSkeleton 0, no dim; Category select and Create button never disabled |
| M4-02 Search ("chair") | Products | **FAIL (dim)**, pass (skeleton) | maxSkeleton 0, no dim; confirmed `query=chair` fired |
| M4-02 Next | Orders (`/order-management/orders`) | **FAIL (dim)**, pass (skeleton) | maxSkeleton 0, no dim |
| M4-02 Sort (Debtor Name) | Orders | **FAIL (dim)**, pass (skeleton) | maxSkeleton 0, no dim |
| M4-02 Filter (Status=Completed) | Orders | **FAIL (dim)**, pass (skeleton) | maxSkeleton 0, no dim; confirmed `order_status_id=...` fired |
| M4-02 Search ("living") | Orders | **FAIL (dim)**, pass (skeleton) | maxSkeleton 0, no dim |
| M4-02 Next | Stock (`/inventory-management/stock`) | **FAIL (dim)**, pass (skeleton) | maxSkeleton 0, no dim |
| M4-02 Sort (Warehouse) | Stock | **FAIL (dim)**, pass (skeleton) | maxSkeleton 0, no dim |
| M4-02 Search ("circular") | Stock | **FAIL (dim)**, pass (skeleton) | maxSkeleton 0, no dim; confirmed `query=circular` fired |
| Column-preference window (hard reload) | Products | PASS | skeleton (700 cells = 14 cols x 50 rows) only 941ms-1952ms during the artificially delayed first paint, permanently 0 after; see samples JSON |
| M4-03 pagination strip during transition | Stock | PASS | Next button + Rows-per-page stayed present and enabled (`disabled` never true) through a 1.2s delayed transition |
| M4-03 double-Next | Stock | PASS | two rapid clicks (60ms apart) fired `page=3` then `page=4`; grid settled on `151 - 200 of 9269` (the later page wins); zero console errors |
| M4-05 search vs. controls | Products | PASS | typing never disabled Category/Brand selects, Create button, or select-all, while filter+search also individually confirmed non-disabling |
| M4-05 search vs. controls | Users (`/user-management/users`, "Administrative Users") | PASS | typing never disabled the 3 advanced-filter controls (Add condition/Apply are inside the "Advanced filters" popover) or "Add user" |
| M4-06 row hover prefetch | Products | **INCONCLUSIVE (browser), PASS (code+vitest)** | see dedicated section below |
| M4-06 sidebar hover prefetch | any leaf link | **INCONCLUSIVE (browser), PASS (code+vitest)** | same dev-mode limitation |
| M4-06 detail pager prefetch on mount | Product detail | PASS (code) | `useListPager.ts:185-188` calls `prefetchOnce` for prev/next hrefs in a `useEffect` on mount; same dev-mode network-capture limitation applies |
| M4-07 filter swap #1 (Decided and undecided -> Still to decide) | SCM Reorder Planning (a plan run) | PASS | 0 console errors, header/column order matched row data after settle |
| M4-07 filter swap #2 (Every price answer -> Fix zero price) | SCM Reorder Planning | PASS | 0 console errors, header/column order matched row data after settle, row set changed (`#16-18...` visible) |
| Regression: Back to list preserves page | Products | PASS | opened a page-2 row's detail, "Back to products" returned to the SAME page 2 (`SRTW1000-SS-CR` visible again) |
| Regression: refetch holds rows | Respond Outbox (`/system-management/respond-outbox`) | PASS | manual refresh with a 900ms delayed fetch: row count held at 50 throughout, maxSkeleton 0 |
| Regression: refetch holds rows | Sponsorship Report (`/procurement-management/sponsorship-forms/report`) | PASS | manual refresh with a 900ms delayed fetch: row count held at 18 throughout, maxSkeleton 0 |

## M4-02 root cause (why it fails identically on all three named grids, not just Products)

The brief called out "Products is the one that failed last time," but this run found the SAME
missing half of the mechanism on Products, Orders, and Stock. Read against the primitive:

- `components/ui/data-grid-table.tsx` (`DataGridTableBody`) computes
  `holdingRows = !showSkeleton && (props.isPlaceholderData || (isLoading && rows.length > 0))`,
  and only `holdingRows` adds `opacity-60`.
- `props.isPlaceholderData` is **never passed** to `<DataGrid>` anywhere in the app -
  `grep -rn "isPlaceholderData=" app components` (excluding tests) returns zero matches.
- The fallback `isLoading && rows.length > 0` therefore has to carry the whole mechanism, but the
  `isLoading` every caller passes is the literal React Query `isLoading` destructured straight off
  `useQuery(...)` (`ProductsList.tsx:229`, `OrdersList.tsx:104`, `StockBalanceGrid.tsx:101` via
  `useStockBalance`) - which, per `LIST_QUERY_OPTIONS`'s own `placeholderData: keepPreviousData`,
  is `false` throughout a page/sort/filter/search change (placeholder data counts as data, so
  `status` is `'success'` the whole time). Only `isFetching` or the query's own
  `isPlaceholderData` field is true during that window, and none of the three callers destructure
  or forward either one.
- Net effect: `holdingRows` is `false` for every transition on every grid checked, and the dim
  never renders. This was independently reproduced with a `window.fetch` patch that delayed the
  real endpoint 500-900ms (so a 1.2-1.8s polling window had every chance to catch it) across five
  interaction types (Next, Prev, sort, filter, search) on three different grids - `opacity-60`
  never appeared once, while the skeleton-suppression half of M4-02 (`showSkeleton` gating) does
  work correctly (0 skeleton cells every time after first paint, matching the hard-reload PASS
  above).
- Fix shape (not applied by this tester role): either wire `isPlaceholderData: query.isPlaceholderData`
  through to `<DataGrid>` at all ~186 call sites (defeats the primitive's stated goal of "a call
  site that never passes `isPlaceholderData` still gets the dim"), or change what callers pass as
  `isLoading` to something that stays true while fetching WITH existing rows (e.g. `isFetching`),
  or add a genuinely automatic path in the primitive that doesn't depend on the caller's naming of
  its query flags at all (e.g. inspect the table's `manualPagination` query key via context). This
  is a report of what's broken, not a design decision for the tester to make.

## M4-06 detail (why it is browser-inconclusive in this environment)

Code read confirms the wiring is correct: `LinkableBodyRow` in `data-grid-table.tsx:539-540` calls
`prefetchOnce(href)` (from `hooks/usePrefetchOnce.ts`, `router.prefetch(href)` at most once per
href) on `onPointerEnter`; `useListPager.ts:185-188` does the same for the prev/next hrefs on
mount; `sidebar-menu.tsx` sets `prefetch={false}` on its `Link`s (no viewport prefetch) and calls
the same `prefetchOnce` hook (confirmed at `sidebar-menu.tsx:114`). Unit tests are green:

```
npx vitest run components/ui/data-grid-table.prefetch.test.tsx   -> 1 file, 4 tests passed
npx vitest run hooks/usePrefetchOnce.test.ts hooks/useListPager.keyParity.test.ts -> 2 files, 37 tests passed
```

Browser attempt: hovered five different fresh Products rows and a sidebar leaf link, each time
with the network log freshly cleared and `hover:none` confirmed `false`. Checked three independent
capture methods - `agent-browser network requests`, a `window.fetch` wrapper that logs every call
with headers, and `performance.getEntriesByType('resource')` (which catches `<link>` prefetches
too, not just `fetch`) - and all three showed **zero** network activity attributable to the hover
in every attempt. This matches a known Next.js `next dev` (Turbopack) characteristic: client Router
`prefetch()` for a dynamic App Router route does not perform an observable network fetch outside a
production build. Functionally, the click-through still worked correctly (row click navigated to
the detail page, zero console errors before/after, `errors` command empty throughout). Given the
task's standing rule to use `npm run dev` and not build, this criterion could not be positively
browser-confirmed in this environment; it is reported here as a limitation, backed by the passing
unit-level tests and a source read, per "Component-level vitest is the autonomous fallback."

## Screenshots in this directory

- `M4-02-products-list-1280.png`, `M4-02-orders-list-1280.png`, `M4-02-stock-list-1280.png` -
  initial 1280px list state for each of the three named grids.
- `M4-02-products-filters-open.png`, `M4-02-products-active-filter-applied.png` - Products filter
  panel and an applied Status=Active filter (Filters badge = 1).
- `M4-02-orders-status-filter-open.png` - Orders' searchable Status dropdown expanded.
- `M4-05-users-list.png`, `M4-05-users-advanced-filters.png` - Users list ("Administrative Users")
  and its "Advanced filters" popover (Add condition / Apply / Clear filters).
- `M4-07-reorder-grid-initial.png`, `M4-07-reorder-filter1-still-to-decide.png`,
  `M4-07-reorder-filter2-fix-zero-price.png` - Reorder Planning grid before and after each of the
  two filter swaps; header stays aligned with the row data in both.
- `regression-products-back-to-list-page2.png` - Products list after Back-to-products from a
  page-2 detail, showing the same row (`SRTW1000-SS-CR`) still present.
- `regression-respond-outbox.png`, `regression-sponsorship-report.png` - the two non-DataGrid-list
  regression targets checked for refetch-holds-rows/no-skeleton.
- `M4-02-column-pref-window-hard-reload-samples.json` - the polling samples for the hard-reload
  column-preference-window check (skeleton only 941-1952ms, then 0).

## Console / network hygiene

Zero uncaught page errors (`errors` command) across the whole session. `console` showed only
`[debug] JWT token extracted successfully` and (once) a Fast Refresh rebuild log line - no
`[error]`-level entries at any point, including during both SCM filter swaps and the double-Next
press.

## Run 2 (after fix round 2, HEAD 208869731, 2 Sep 2026)

Targeted re-verification of the M4-02 dim clause (the blocker above) plus the behaviours that
changed since (M4-03 pager-under-dim, the newly-forwarded object-shaped call sites, the two
hand-wrapped tags, the pager-skeleton-on-first-load nit, the newly-spread `keepPreviousData`
lists, and the Back-to-list regression). Worktree `motion2-M4`, branch
`feat/motion2-M4-list-latency`, `PORT=3081 npm run dev` (own session), BE reused read-only on
`:8120`. Login via `E2E_EMAIL`/`E2E_PASSWORD` from `.env.local`. Viewport 1280x800. Sessions
`--session m4run2` (main) and `--session m4reload` (the one hard-reload check that needed a
runtime init script, closed immediately after). Navigated by sidebar clicks from `/`, never a
deep URL, except the one already-reached page reloaded in place for the pager-skeleton check.

Method: same in-page `window.fetch` patch adding a 500-1300ms delay to the grid's own list
endpoint, then a tight 20-30ms poll of `document.querySelector('table')`'s
`[data-slot="skeleton"]` count and the `<tbody>` class list for `opacity-60`, run in a single
`eval` call together with the triggering click/keystroke (a separate CLI round-trip between
trigger and poll start is ~1.5-3.5s and would miss the window entirely). `network requests`
independently confirms each interaction fired the request it claims to.

### M4-02 dim clause: 12/12 PASS (the blocker is fixed)

The fix (`refactor(datagrid): one skeleton gate` + the per-module `isPlaceholderData` forwarding
commits, `c87b48631`..`fd1771058`..`208869731`) wires each list hook's `isPlaceholderData` field
through to `<DataGrid>`, which the tester's Run 1 report identified as the missing half. All
twelve combinations across Products, Orders and Stock now dim correctly.

| # | Grid | Action | maxSkeleton | opacity-60 seen | Cleared after |
| - | --- | --- | --- | --- | --- |
| 1 | Products | Next | 0 | yes | yes |
| 2 | Products | Sort (Product Code) | 0 | yes | yes |
| 3 | Products | Filter (Status=Active) | 0 | yes | yes |
| 4 | Products | Search ("chair") | 0 | yes | yes (confirmed by a follow-up read a moment after the poll window closed; two sequential `query=chair` requests fired for page 1 then page 2, a dev-mode double-effect artifact, not a defect) |
| 5 | Orders (Delivery Orders in the sidebar, `/order-management/orders`) | Next | 0 | yes | yes |
| 6 | Orders | Sort (Debtor Name) | 0 | yes | yes |
| 7 | Orders | Filter (Status=Completed) | 0 | yes | yes |
| 8 | Orders | Search ("living") | 0 | yes | yes |
| 9 | Stock | Next | 0 | yes | yes |
| 10 | Stock | Sort (Warehouse) | 0 | yes | yes |
| 11 | Stock | Filter (Status=Low) | 0 | yes | yes |
| 12 | Stock | Search ("circular") | 0 | yes | yes (same late-clear pattern as #4; confirmed cleared by a follow-up read) |

Raw measurements (all twelve, `{maxSkeleton, sawDim, clearedAfter}` from the in-page poll):

```
Products Next:            {maxSkeleton: 0, sawDim: true,  clearedAfter: true}
Products Sort:            {maxSkeleton: 0, sawDim: true,  clearedAfter: true}
Products Filter (Active): {maxSkeleton: 0, sawDim: true,  clearedAfter: true}
Products Search (chair):  {maxSkeleton: 0, sawDim: true,  clearedAfter: false at 2600ms, confirmed true on follow-up read}
Orders Next:               {maxSkeleton: 0, sawDim: true,  clearedAfter: true}
Orders Sort (Debtor Name): {maxSkeleton: 0, sawDim: true,  clearedAfter: true}
Orders Filter (Completed): {maxSkeleton: 0, sawDim: true,  clearedAfter: true}
Orders Search (living):    {maxSkeleton: 0, sawDim: true,  clearedAfter: true}
Stock Next:                {maxSkeleton: 0, sawDim: true,  clearedAfter: true}
Stock Sort (Warehouse):    {maxSkeleton: 0, sawDim: true,  clearedAfter: true}
Stock Filter (Low):        {maxSkeleton: 0, sawDim: true,  clearedAfter: true}
Stock Search (circular):   {maxSkeleton: 0, sawDim: true,  clearedAfter: false at 2600ms (poll loop itself ran only 7 of the expected ~86 ticks, an environment hiccup, not a product issue), confirmed true and query=circular fired via network log on follow-up read}
```

### M4-03 pagination strip during the dim: PASS

On Stock, with the same 900-1300ms delay: clicked Next, then 60ms later (before the response
could resolve) read `disabled` off the rows-per-page combobox, the Next button and the Prev
button - all three `false` throughout the window - then clicked Next again immediately. The grid
settled on `101 - 150 of 9269` (page 3), confirming the second press wins. Screenshot:
`run2-M4-03-stock-double-next-page3.png`.

### Object-shaped call sites: 4 of 5 exercised, all clean; 1 wiring-confirmed but data-starved

- **Stock Transfers** (Inventory > Stock Transfers, `/api/v1/inventory/stock-transfers`): Next -
  `{maxSkeleton: 0, sawDim: true, clearedAfter: true}`, zero console errors.
- **Loading Plan** (Supply Chain > Planning > Loading Plan, `/api/v1/scm/loading-plans`): only 1
  row in this tenant's data, so Next couldn't be exercised; sorted by Supplier instead -
  `{maxSkeleton: 0, sawDim: true, clearedAfter: true}`, zero console errors. Screenshot:
  `run2-M4-object-loading-plan.png`.
- **Plans** (Supply Chain > Project Demand > Plans, `/api/v1/project-sales/plans`): no pagination
  controls rendered (dataset fits one page); sorted by Customer -
  `{maxSkeleton: 0, sawDim: true, clearedAfter: true}`, zero console errors.
- **Stock Debt** (Supply Chain > Project Demand > Stock Debt, `/api/v1/project-sales/stock-debt`):
  Next - `{maxSkeleton: 0, sawDim: true, clearedAfter: false at 1800ms, confirmed cleared on a
  follow-up read}`, zero console errors. Screenshot: `run2-M4-object-stock-debt.png`.
- **Project Sales > a project > Sales orders tab**
  (`/api/v1/project-sales/projects/{id}/sales-orders`): the wiring is confirmed by source read
  (`SalesOrdersPanel.tsx:401` forwards `salesOrders.isPlaceholderData`), but this tenant's data
  could not exercise it live - all 5 seeded projects (PRJ-000001 through PRJ-000005) show
  "0 sales orders" / "No sales order drafted yet". Confirmed the empty state itself renders
  cleanly with zero console errors. Screenshot: `run2-M4-object-sales-orders-empty.png`.

### The two hand-wrapped tags: both render, PASS

- **Inventory > Stock > a stock row > Stock Ledger**: opened `1/2" ULTRA CIRCULAR at BRW-BB`
  (`/inventory-management/stock/{id}/{id}`); the "Stock Ledger" table renders inline in the detail
  page with real `BULK_IMPORT` / `SYSTEM_ADJUSTMENT` rows, zero console errors. Screenshot:
  `run2-M4-wrapped-stock-ledger.png`.
- **SLA > Conversation SLA Tracking > a record > Event Log**: opened a `+60999118984` tracking
  record and its "Event Log" tab; the table renders 2 `Adjust` event rows, zero console errors.
  Screenshot: `run2-M4-wrapped-sla-event-log.png`. Note: `agent-browser click @ref` on this
  particular list row silently did not register (URL unchanged); a native `element.click()` via
  `eval` worked immediately. Read as a tool/timing quirk on this row type, not a product defect -
  the feature itself works once triggered, and the same list's own row-click elsewhere in this
  run (Products, Orders, Stock) worked fine via the normal `click @ref` path.

### Pager skeleton on first load (nit 7): PASS

Hard reload of Products with a runtime `agent-browser addinitscript`-equivalent (a fresh session
launched with `--init-script`, since the daemon's `addinitscript` runtime command referenced in
the skill docs is not present in the pinned 0.27.0 build) that both delayed the products/
column-config fetches 900-1300ms and polled every 20ms from t=0 for 4000ms. Full samples:
`run2-M4-pager-skeleton-hard-reload-samples.json`. Summary: `hasPagerButtons` (the real
"Go to next page" control) stays `false` for the entire delayed-fetch window (t=0 to ~2589ms,
during which `tableSkeletons` reads 700 = 14 cols x 50 rows), flips `true` at t=2819ms once first
paint completes, and never reverts to skeleton through the rest of the 4s window. Combined with
the M4-02 Next-click measurements above (`maxSkeleton: 0` on every subsequent page/sort/filter/
search), this confirms the pager shows skeleton bars only until first paint and never again
during paging.

### Newly-spread lists (first time on `keepPreviousData`)

| List | Endpoint | Result |
| --- | --- | --- |
| Picking Lines (Procurement) | `/api/v1/procurement/picking-lines` | Next: `{maxSkeleton: 0, sawDim: true, clearedAfter: true}`, zero console errors |
| Stock Claims (Project Sales) | `/api/v1/project-sales/allocation-claims` | Empty state in this tenant ("No stock has been borrowed either way") - no rows to page; zero console errors |
| Parties (Project Sales) | `/api/v1/project-sales/parties/` | Loads all rows in one request (`limit=200`, no `page` param) and sorts client-side; a sort-header click fired no new network request, so the dim mechanism (which only fires on an actual refetch) is not exercised here - not a defect, this list is not server-paginated. Zero console errors |
| Awaiting Acceptance (Project Sales) | `/api/v1/project-sales/leads/awaiting-acceptance` | Single page of data in this tenant, no Next/Prev controls; a sort-header click on "Value" fired no new request (client-side sort on this small dataset). Zero console errors |
| Automation (System > Configuration) | `/api/v1/system/automation/automations` | Same pattern - sort click on "Name" fired no new request (`limit=50` load-all). Zero console errors. Screenshot: `run2-M4-spread-automation.png` |
| Email Templates (System > Messaging) | `/api/v1/system/email-templates` | Same pattern - sort click on "Name" fired no new request (`limit=50` load-all). Zero console errors |

None of the six showed a console error or a stuck/empty render; the three with real
paginated/sorted server round trips (Picking Lines, plus the object-shaped ones above) all held
rows and dimmed correctly. The other three do their sort/filter client-side against a
fully-loaded page and never re-fetch, so the M4-02 mechanism has nothing to exercise there - this
is a dataset/list-shape fact, not a regression.

### Regression: Products detail then Back to list keeps page AND filters - PASS

Applied Status=Active (Filters badge "1"), advanced to page 2 (`51 - 100 of 11673`), opened the
first row's detail (`SRTWC7604-WEPLS-SC`; URL carried
`?page=2&limit=50&sort=created_at&dir=desc&status=active`), then clicked "Back to products".
Landed back on the exact same page 2 with the same first row and the Filters badge still reading
"1". Zero console errors. Screenshot: `run2-M4-regression-back-to-list.png`.

### Incidents during this run (both resolved, neither is a product defect)

- A tool-level `agent-browser click @ref` intermittently failed to register on certain button
  elements (a numbered pager button, the SLA tracking row) - confirmed by URL/state staying
  unchanged. A native `element.click()` dispatched via `eval` on the exact same element worked
  immediately every time. Read as a click-coordinate/ripple-timing quirk in the driver, not an
  app bug, since the underlying feature works once the click actually lands (and the same
  interaction pattern succeeded via normal `click @ref` on other rows/buttons in this same run).
- The `PORT=3081 npm run dev` background process was killed by the environment mid-run (its log
  shows a clean `[killed]` after a stretch of `ECONNREFUSED` to the `:8120` backend from another
  lane going briefly unreachable and then recovering - unrelated to anything this tester ran).
  Restarted immediately (`npm run dev` from `sorento_crm_frontend/`, new PID), confirmed
  `lsof -i :3081` back up, and re-verified state before continuing; the regression check above
  was run entirely after the restart.

### Conclusion

The M4-02 blocker from Run 1 is fixed: all twelve dim-clause combinations pass, M4-03 continues
to pass, the newly-touched object-shaped call sites and hand-wrapped tags render and dim
correctly where the tenant has data for it, the pager-skeleton nit is confirmed end-to-end, and
the Back-to-list regression still holds page and filters. No new console errors anywhere in this
run.

## Run 3 (after fix round 3, HEAD 8c814baae, 2 Sep 2026)

Short targeted re-verification of the six named grids/lists for round 3 plus the MCP tools
"revert" check and the Drive list view. Worktree `motion2-M4`, branch
`feat/motion2-M4-list-latency`, `PORT=3081 npm run dev` (own session, PID group under parent
`npm exec` 39313 / `next-server` child 39310), BE reused read-only on `:8120` per
`FASTAPI_INTERNAL_URL=http://localhost:8120` in `.env.local` (confirmed alongside
`NEXTAUTH_URL=http://localhost:3081`, `AUTH_TRUST_HOST=true`, no `NEXT_PUBLIC_API_URL`). Login via
`E2E_EMAIL`/`E2E_PASSWORD` from `.env.local`. `lsof -i :3081` was empty before starting. Sessions
`--session m4run3` (main), `--session m4areload` and `--session m4areload2` (the two hard-reload /
`--init-script` checks, both closed immediately after use). Navigated by sidebar clicks from `/`,
except the two `--init-script` sessions which needed a fresh login (isolated session) before
reaching the target page by the same sidebar-click method.

Method: same in-page `window.fetch` patch (500-1200ms artificial delay on the grid's own list
endpoint) plus a 20-25ms poll of `document.querySelector('table')`'s `[data-slot="skeleton"]`
count and the `<tbody>` class list for `opacity-60`, run together with the triggering
click/keystroke inside one `eval` call so no CLI round-trip can miss the window. For the two
cold-reload checks (Drive list first paint), a `--init-script`-registered patch armed the delay
and a background poll loop before `location.reload()`/`location.href` navigation, since the
runtime `addinitscript` command is still not present in the pinned 0.27.0 build (matches Run 2's
finding). `network requests --filter` independently confirmed each interaction's request. Where
`agent-browser click @ref` silently failed to register (the sidebar's "Operations"/"AI Assistant"
group toggles, and one sidebar leaf link), a native `element.click()` via `eval` on the same
element worked immediately - the same tool quirk Run 2 already logged, not a product defect.

### Check 1: rows held and dimmed on a page turn / sort / filter

| # | Grid | Trigger | Result | Observation |
| - | --- | --- | --- | --- |
| 1 | Project Sales > Leads | Status filter Open -> Qualified (no Next/Prev, single page) | PASS | maxSkeleton 0, `opacity-60` seen and cleared; `outcome=qualified` request confirmed 200 |
| 2 | Project Sales > Pipeline (grid view) | Sort by "Code" (only page has 5 rows, no Next/Prev) | PASS | maxSkeleton 0, dim appeared at t=37ms and held through the full 900ms artificial delay, cleared at t=1047ms once `sort=project_code` resolved |
| 3 | System Management > API Call Log | Next page | PASS | held 50 rows, dimmed t=106ms-1149ms, `page=2` request confirmed |
| 4 | SLA Management > Message Snippets | Search ("widget"); tenant has zero snippets, single "No snippets yet" placeholder row | PASS | the empty-state row itself dims correctly (t=234-994ms) during the `query=widget` fetch, then clears - the mechanism engages even with no real data to hold |
| 5 | SCM > Reorder > a run's results grid | Next page, then all 4 filter comboboxes (status, decided/undecided, price answer, suggested action, level answer) | **N/A** | the recommendations endpoint loads with `limit=1000` at mount and the 25-row/page pager plus every filter combobox is client-side against that already-loaded set - zero new `/api/v1/scm/*` requests fired for any of the 5 triggers tried. Per the brief's fallback instruction, marked n/a rather than forced. Also note: every visible run in this tenant shows status "Planning", not "Completed" - the most recent run was used since none was in a Completed state to pick from |
| 6 | SCM > Policies > Reorder policies tab | Search ("PROJECT") | PASS | held 8 rows dimmed t=281-1228ms, cleared to the 2 matching rows once `query=PROJECT` resolved |

Screenshots: `run3-leads-filter-qualified.png`, `run3-pipeline-grid-sort.png`,
`run3-api-call-logs-next.png`, `run3-message-snippets-search.png`,
`run3-reorder-run-clientside.png`, `run3-reorder-policies-search.png`.

**Secondary observation on Pipeline (grid view), not a required check outcome:** toggling the
"Critical only" switch to a filter combination that narrows the result set to genuinely ZERO rows
(no critical projects exist in this tenant) blanks straight to the empty-state row at t=76ms -
well before the artificially-delayed fetch resolves at t~1027ms - rather than holding the previous
5 rows dimmed through the wait. The sort transition on the same grid (row 2 above, same 5 rows,
count never reaches zero) dims correctly, so the mechanism itself works on this list; it is
specifically the "next result set is empty" case that skips the hold. Flagging for a follow-up
look, not fixed here.

**Finding independent of M4, surfaced by check 6:** the Reorder Policies tab returns duplicate
rows for the same policy even on a bare page load, before any search - `PROJECT`, `ACC-AT` and
`SRT-BA` scope rows each render twice (confirmed both by reading rendered row text and by a
`[error] Encountered two children with the same key` React console warning repeating for the same
3 policy UUIDs throughout the session). This is a pre-existing data/dedup defect in that list, not
a round-3 regression - it is called out here only because it produces the real console errors
counted in Check 4 below. Not something for a tester to fix; worth its own ticket.

### Check 2: MCP tools catalogue Active-only toggle (revert check)

PASS. Flipping "Show deactivated" from the System Management > MCP Tools page dropped the
previous 40 active-only rows to a single loading row almost immediately (t=23ms, well before the
artificially-delayed `is_active=false` fetch resolved at t=860ms) rather than holding or dimming
them, then swapped in the full 201-row deactivated set once the response arrived (t=904ms). This
is the revert from commit `396825950` ("the catalogue must not answer from the previous filter")
holding: no stale rows survive the filter flip. Zero console errors. Screenshot:
`run3-mcp-tools-toggle.png`.

### Check 3: Resource Management > Attachment directories, list view

PASS, both halves.

- **Cold first load** (`location.reload()` on the list-mode Drive page, delay armed via
  `--init-script` since no runtime `addinitscript` exists in this build): no table for ~970ms,
  then real skeleton bars appear (300 skeleton cells = 6 cols x 50 rows) and taper to 150 then 0
  by t=2905ms as the column-config and row data both resolve - confirms skeleton-then-rows on a
  genuine cold mount. Screenshot: `run3-drive-coldload-skeleton.png`.
- **Folder navigate in and back** (root "All files" with 50 rows -> click into "Marketing", 23
  rows -> click "All files" to return): both directions held the CURRENT row count with
  `skelCount: 0` for the entire 800-1000ms artificial delay before flipping cleanly to the new
  row count once the (delayed) `attachments/drive` request resolved (t=1013ms in, t=819ms out) -
  no skeleton reappeared after the first paint in either direction. Column headers
  (`""`, `Name`, `Modified`, `Company`) were identical before and after both transitions - no
  default-column flash. Screenshot: `run3-drive-list-view.png`.

### Check 4: console errors across all of the above

**FAIL, isolated to the Reorder Policies tab (SCM > Policies).** `console` showed 56 repeats of
`[error] Encountered two children with the same key, '%s'. ... <uuid>` cycling through 3 policy
UUIDs, matching the duplicate-row finding under Check 1 row 6 above. Every other page and
interaction in this run - Leads, Pipeline (both the sort and the critical-filter edge case), API
Call Log, Message Snippets, the Reorder run results grid, MCP Tools, and both Drive list checks -
produced zero console errors and zero uncaught page errors (`errors` command empty throughout).
The failure is a pre-existing data/render defect (duplicate policy rows -> duplicate React keys),
not a round-3 list-latency regression; it is reported here because the brief's check is worded as
a blanket "zero errors across all of the above" and this run did surface a real one.

### Cleanup

Dev server killed (`kill 39313`, its `next-server` child 39310 exited with it; confirmed via a
follow-up `lsof -i :3081` returning empty). Only the `m4run3`, `m4areload` and `m4areload2`
agent-browser sessions belonging to this run were closed - no `close --all` was issued.
