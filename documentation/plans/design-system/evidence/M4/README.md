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
