# M5 browser evidence run 1

Lane: `feat/motion2-M5-shells-and-list-rules`, HEAD `39df4b4f4`. FE `http://localhost:3081`, BE
`http://localhost:8120`. Tool: `agent-browser@0.27.0`, isolated `--session m5-evidence`. Read-only
throughout - no Delete/Archive/Unlink/Confirm/Send/Save clicked on any real record, no deferred-action
countdown armed, no text typed into the conversation composer.

Contract: UAC M5-01..M5-08, `documentation/plans/design-system/ui-motion-round2-acceptance-criteria.md`;
PLAN section 3.5, `documentation/plans/design-system/PLAN-ui-motion-round2.md`.

Session note: the shared daemon reset this session to `about:blank` twice mid-run (another agent's
`open`/interference, or daemon churn - `--session` isolates the browser instance but the daemon
itself is still shared machine-wide). Re-logged in both times and continued; noted at the point it
happened. `get url` was checked before trusting reads throughout.

## Results

| UAC | Route | Viewport | Result | Numbers | PNG |
| --- | --- | --- | --- | --- | --- |
| M5-05 sticky header | Products (`/master-data-management/products`) | 1280x800 | pass | scroller top=258, height=480, scrollHeight=3040 (50 rows); scrolled to row 40 (scrollTop=2400), header stayed at top=258 | `01-products-1280-landing.png`, `04-products-1280-landing.png`, `05-products-1280-scrolled-row40.png` |
| M5-05 sticky header | Sales Orders / "Orders" (`/scm/sales-orders`) | 1280x800 | pass | bumped rows-per-page 25->50 via combobox (native `<select>` didn't work, custom listbox did); scroller top=258, scrollHeight=3040; scrolled to row 40, header stayed at top=258 | `02-orders-1280-landing.png`, `03-orders-1280-scrolled-row40.png` |
| M5-05 sticky header | Stock (`/inventory-management/stock`) | 1280x800 | pass | scroller top=258, scrollHeight=3040 (already 50 rows); scrolled to row 40, header stayed at top=258 | `08-stock-1280-landing.png`, `09-stock-1280-scrolled-row40.png` |
| M5-05 sticky header | Stock | 375x667 | pass | landing: scroller rect top=324, height=347, bottom=671 (4px past the 667 fold - rounding, not a real overflow); **5 full 60px rows fit** (347/60=5.78), a 6th partial row visible; scroller TOP is well above the fold (324 < 667) - **no document scroll needed to see the grid**, toolbar did not wrap; scrolled to row 40, header stayed pinned at top=324 | `10-stock-375-landing.png`, `11-stock-375-scrolled-row40.png` |
| M5-05 sticky header | Products | 375x667 | pass | landing: scroller top=330, bottom=677 (10px past fold, same rounding note); 50-row page-size preference persisted from the 1280 pass; scrolled to row 40, header stayed pinned at top=330 | `12-products-375-landing.png`, `13-products-375-scrolled-row40.png` |
| M5-05 sticky header | Sales Orders | 375x667 | pass | page-size did NOT persist across the viewport/nav change (reset to 25) - bumped to 50 again; toolbar wraps to 2 rows on this list (Search / Filters+Columns+Export / Actions+Start) but scroller top is still 356, well above the 667 fold - **toolbar wrap does not push the grid below the fold**; header stayed pinned at scroller top through the scroll | `14-orders-375-landing.png`, `15-orders-375-scrolled-row40.png`, `15b-orders-375-scrolled-row40-docTop.png` |
| M5-05 resize/drag, no per-list prop | Products | 1280x800 | pass | Resize: dragging the "Product Code" resize handle 100px (690->790 at y277) grew the column 345px->445px. **Note:** the resizer's own box is 16px wide (`w-4`, `-end-2` offset) but the header cell has `overflow:hidden` (`truncate`), which clips the handle to an effective ~8px hit area on its LEFT edge only (686-694 of the 686-702 box) - clicking the geometric centre of the rendered handle (694) landed on the plain `<th>`, not the resizer, and did nothing; clicking inside the un-clipped 8px band worked. Drag-reorder: dragging the "Product Code" header (x~438) onto "Category" (x~1169) reordered columns from `[Product Code, Product Name, Category, ...]` to `[Product Name, Category, ..., Created, Product Code, Updated, ...]` (moved past Created). Both worked with zero per-list config (`columnsResizable`/`columnsDraggable` defaults). | `06-products-1280-column-resized.png`, `07-products-1280-column-reordered.png` |
| M5-05 pinned column vs header (review S3) | Stock Debt (`/project-sales/stock-debt`) | 1280x800 | pass | **No list with a user-facing "pin" affordance exists anywhere in the app today** - `data-grid-column-header.tsx`'s own comment (line ~328) confirms `headerControls` (Move/Pin/Hide menu) is dead code, never rendered on main. The ONLY grid with a column pinned by default is `StockDebtClient.tsx` (`initialState.columnPinning: { left: ['product'] }`), and that route has **no sidebar/topbar/in-app link anywhere** - reached it via deep URL as a one-off exception (see Findings). Scrolled the grid vertically: a pinned header cell measured `z-index:6, position:sticky`; a pinned body cell measured `z-index:5, position:sticky` - header wins the stacking order, confirmed visually mid-scroll (Product column stayed fixed left, Sep26...Mar27 columns and rows scrolled under/past the header cleanly, no visual collision). | `16-stockdebt-1280-landing.png`, `17-stockdebt-1280-midscroll-pinned.png` |
| Double scroll (review B2) | Fulfilment Planning board cell breakdown dialog (`/project-sales/fulfilment-planning` -> select 2 rows -> Plan together -> click a board cell) | 1280x800 | **fail** | Found **4 nested elements with `overflow-y:auto` and `scrollHeight > clientHeight` simultaneously visible** inside the dialog: (1) the dialog body wrapper (`min-h-0 flex-1 ... overflow-y-auto`, 550/377), (2) a `max-h-[50vh] ... overflow-y-auto` table wrapper (719/287), (3) a `max-h-[35vh] ... overflow-y-auto` nested panel (339/202), (4) the DataGrid's own bounded scroller (`max-h-(--grid-max-h) overflow-y-auto`, 1045/257). Proved independent (not just CSS-present-but-inert) by setting the outer dialog body's `scrollTop` directly (173->100) and confirming the visible content shifted while the inner table's own scroll position did not move - two scroll regions moving independently, i.e. more than ONE vertical scrollbar. Read-only: opened, inspected, closed with Escape. | `20-boardcell-dialog.png`, `21-boardcell-dialog-outerscroll.png` |
| M5-07 back-to-list, row-click case | Products page 2, row 38 (`SRTBF11710`) | 1280x800 | **fail** | Row click correctly appended `from=<row id>` to the detail href (`?page=2&limit=50&sort=created_at&dir=desc&from=e4f01fba-...`). Pressed browser Back: landed on **bare `/products` with NO query string at all** - `page` and `from` both gone, pagination silently reset to page 1 (`Go to previous page` disabled). `SRTBF11710` (row 38) is on page 2, so it is not even rendered, and `document.querySelector('[data-returned="true"]')` found nothing. Repeated as a page-1 control case (row 10, `SRTWT812`): Back again lands on bare `/products`, `from` absent, `data-returned` absent - so the gap is not page-2-specific, it reproduces from page 1 too. Root cause read from source: `appendListState` (`components/ui/data-grid-table.tsx`) writes `from=` only into the DETAIL href via `router.push`; nothing ever writes `from=` (or the current page) into the LIST route's own history entry, so the browser's actual "back" always returns to the list's ORIGINAL bare URL from first mount, which never carried the param the restore logic (`useReturnedRowId`, reading `window.location.search`) depends on. | `22-product-detail-row38.png`, `23-products-after-back.png`, `24-products-after-back-page1-control.png` |
| M5-07 back-to-list, detail pager case | Products, 3x "Next product" from the row-10 detail, then Back | 1280x800 | **fail (+ scope note)** | Each Next press carried `from=` matching the NEW landing product, confirming `useListPager` does carry `from` forward as documented. But the pager uses `router.push` per step (4 total pushes: row-click, Next, Next, Next), so **ONE Back only steps back ONE product in the pager chain**, landing on `.../ed225a54-...?...&from=ed225a54-...` (a detail page), not the list - contrary to the brief's "press Back once" framing. Pressed Back 3 more times (4 total) to actually reach the list: landed on bare `/products` again, `data-returned` absent - same root cause as the row-click case above. | `25-products-after-pager-then-back.png` |
| M5-03 loading shift | Products | 1280x800 | pass | Title rect and first-row rect measured identical before and after a navigate-away-and-back round trip (Products -> Stock -> Products): title `top=90` both times, first row `top=298` both times. No vertical shift. | (measured via `eval`, no dedicated PNG - see `01`/`04` for the landing state) |
| M5-01 loading flash | Products -> Stock | 1280x800 | not verifiable (too fast) | `next dev` HMR client-side nav resolved before the screenshot command returned; `[role="status"][aria-label="Loading"]` was already gone. Landing screenshot confirms the destination rendered correctly, no stale/broken intermediate state. | `26-loading-flash-stock.png` |
| M5-01 skeleton shape | `project-sales/pipeline` | 1280x800 | pass (with a scope note) | This route's FIRST compile in this dev session ("Fast Refresh done in 242ms") was slow enough to catch mid-load: the captured skeleton is a **3-column grid of card-shaped boxes**, not `ListPageSkeleton`'s row bars. Pipeline defaults to a card/kanban view (a "grid card" vs "table" toggle is visible, card view selected) - the row-bar `loading.tsx` Suspense fallback (confirmed by source: `import { ListPageSkeleton } from ...; return <ListPageSkeleton />`) either painted for less than one frame before the client component mounted, or the client component's OWN internal data-loading skeleton (card-shaped, matching its default view) took over immediately. See Findings - not a fail of M5-01 as literally scoped (the `loading.tsx` file is correct per source) but worth the captain's attention. | `27-pipeline-landing.png` |
| M5-01 skeleton shape | `resource-management/trash` | 1280x800 | pass | Captured mid-load: title/breadcrumb + a real (non-skeleton) toolbar, with the folder panel and the grid BODY as row-shaped grey bars, header row also skeletal - matches `ListPageSkeleton` exactly. | `28-trash-landing.png` |
| M5-01 skeleton shape | `workflow-forms-management/definitions` | 1280x800 | not verifiable (too fast) | Only 1 row of real data; resolved before the screenshot fired. Source confirms `ListPageSkeleton` import. | `29-definitions-landing.png` |
| M5-01 no duplicate header | `user-management/contacts/[id]` (via `/user-management/contacts` -> click a row) | 1280x800 | pass | `document.querySelectorAll('h1')` returned exactly 1 element (`"Contact Details"`) on the loaded detail page - matches the UAC's documented review fix (`bodyOnly` skeleton variant for this route to avoid a second title/crumb bar). | `30-contact-detail-loading.png`, `31-contact-detail-loaded.png` |
| M5-01 no table-flash | Dealer Kit catalogue page detail (`/dealer-kit/pages/[id]`) | 1280x800 | not applicable - see M5-04 row below | Clicking into a real catalogue page tripped `app/(protected)/error.tsx` (a genuine, unrelated `<PageEditor>` bug - see Findings), so no editor/canvas ever rendered to check for a table-shaped flash. | `32-catalogue-page-error.png` |
| M5-04 shell survives a real throw | Same Dealer Kit catalogue page detail | 1280x800 | pass (real throw, not forced) | `<PageEditor>` threw `TypeError: Cannot read properties of undefined (reading '0')` (console: "handled by the `<ErrorBoundaryHandler>` error boundary"). Rendered result: `app/(protected)/error.tsx`'s shipped copy exactly - "Something went wrong" / "Something went wrong on this page." + `Try again` + `Back to dashboards`, with the **full sidebar (Supply Chain, Procurement, Inventory, Products, Dealer Kit expanded, ...) and topbar intact**. `document.body.innerText` confirmed no raw error message and no `Reference:` line (client throw, no `error.digest` - correctly conditional per the AC). Clicked "Try again": no full reload (URL unchanged, SPA-in-place), the boundary re-rendered and hit the SAME deterministic bug again (dev error-overlay issue counter went 2->3) - Reset attempted recovery correctly; it just can't succeed against a genuinely broken component. | `32-catalogue-page-error.png`, `33-catalogue-page-after-tryagain.png` |
| M5-04 not-found inside shell | `user-management/contacts/00000000-0000-0000-0000-000000000000` (deep URL explicitly allowed by the brief) | 1280x800 | pass | Renders the page's own inline "Contact not found" + "Back to contacts" button, plus a toast ("Respond Contact not found. Someone might have deleted it already."), all INSIDE the full shell (sidebar, topbar, breadcrumb). Matches the UAC's documented state exactly (`not-found.tsx` scaffold not yet adopted here; this route's own inline branch is the "first candidate" the plan names). | `34-contacts-unknown-id-404.png` |
| M5-06 | - | - | skipped | `[vitest]`-only per the brief. |

## Findings for the captain

1. **M5-07 back-to-list does not work via the browser Back button, in either tested shape.**
   `appendListState` writes `from=<row id>` only into the DETAIL href (`router.push`), never into
   the LIST route's own history entry. Because the list never pushes its own state (page, sort,
   `from`) to the URL bar, EVERY browser Back from a detail page returns to the list's original
   bare URL from first mount - no `from`, no page, `data-returned` never fires. Reproduced twice:
   row 38 on page 2 (list resets to page 1, target row isn't even rendered) and a row-10-on-page-1
   control case (same bare-URL result). The pager case adds a second problem: `router.push` per
   Next/Prev step means N pager steps need N+1 Back presses to even reach the list, not the "press
   Back once" the brief assumed (which implies a `router.replace`-based pager was the design
   intent). The `[vitest]` coverage cited in the UAC (`data-grid-table.listState.test.tsx`,
   `useListPager.test.ts`) tests the row-highlight/pager-carry logic GIVEN a URL that already
   contains `from=` - it does not exercise an actual browser history round trip, which is exactly
   where this breaks. This is the single biggest gap found in this run and blocks M5-07's
   `[browser]` acceptance as written.

2. **Nested/double scroll confirmed in the Fulfilment Planning board cell breakdown dialog**
   (`BoardCellBreakdownDialog.tsx`), matching review concern B2 almost exactly: 4 simultaneously
   scrollable `overflow-y:auto` regions (dialog body, a `max-h-[50vh]` table wrapper, a
   `max-h-[35vh]` nested panel, and the DataGrid's own bounded scroller), with two of them proven
   to move independently by direct measurement. This is a different dialog than the ones named in
   the brief (SCM Reorder's plan-row dialog was not reached; Project Sales fulfilment board WAS
   reached and is where this lives), so it satisfies "one dialog that holds a grid" but the finding
   itself is a fail, not a pass.

3. **Column resize hit-area is narrower than its drawn box on every grid using this pattern.**
   The resize handle (`w-4`, 16px, offset `-end-2`) sits half inside/half outside its `<th>`, and
   the `<th>` carries `overflow:hidden` (`truncate`) - clipping the handle's usable hit area to
   ~8px on the left side only. Not a functional fail (resize DOES work when clicked in the
   un-clipped band) but worth a follow-up ticket since it makes the handle harder to grab than its
   visual/cursor affordance (`cursor-col-resize` shows over the full 16px) suggests, on every one
   of the ~200 grids using this shared component.

4. **Unrelated, real defect found in passing: `<PageEditor>` throws on Dealer Kit catalogue page
   detail** (`/dealer-kit/pages/[id]`), `TypeError: Cannot read properties of undefined (reading
   '0')`. Reproducible on the first real catalogue page clicked into. Out of scope for M5 to fix,
   but it usefully proved M5-04's error boundary live (see the M5-04 rows above) and should be
   filed separately - it currently blocks reaching the design canvas at all, so the M5-01
   "no table-shaped flash on the canvas" check could not be completed.

5. **No user-facing way to pin a column exists anywhere in the app** (`headerControls` dead per
   the file's own comment) - `columnsPinnable: true` is a default with no UI affordance today
   except the one list (`StockDebtClient.tsx`) that hardcodes `initialState.columnPinning`. That
   list has zero in-app navigation path (no sidebar entry, no topbar link, no in-app `<Link>`
   anywhere in the codebase pointing at `/project-sales/stock-debt`) - reached it by deep URL as
   the only way to exercise the M5-05/S3 pinned-column check at all. Worth a captain's call on
   whether Stock Debt needs a nav entry, independent of M5.

6. **Two Rows-per-page selectors reset per navigation.** Sales Orders' 50-row preference did not
   survive a navigate-away-and-back or a viewport change, unlike Products/Stock where it did.
   Minor, noted in case it's relevant to a future personalization pass - not part of this UAC.

7. Two mid-run session interruptions (daemon reset to `about:blank`, losing the login) cost time
   but did not affect the validity of any completed check above - each was caught via `get url`
   before continuing, and the browser was fully re-authenticated before resuming.
