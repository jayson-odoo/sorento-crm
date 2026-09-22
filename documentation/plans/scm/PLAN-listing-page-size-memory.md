# PLAN: rows-per-page is remembered per user per listing, like column order

Status: implemented, review round 1 addressed (23 Sep 2026). Track: small fix.
UAC: `listing-page-size-memory-acceptance-criteria.md`
Domain: scm (owner report on the fulfilment planning board list view), seam is the shared DataGrid column-config store

## Why

Owner, 22 Sep 2026, on `/project-sales/fulfilment-planning?orders=SO422539`: some users
prefer 50 or 100 rows on "Every contributing line". They pick it, and the next open is back
at 25. Column order and visibility survive a reopen, rows per page does not.

## Measured facts (primary checkout, `origin/main` 2280975f9, 22 Sep 2026)

| fact | where |
| --- | --- |
| Board list view renders `PanelDataGrid` with `listingKey="projects.projects.view::project-fulfilment-board-list-v1"`, `pageSize={25}` | `FulfilmentBoardListView.tsx:629,690` |
| `PanelDataGrid` holds `pagination` as plain `React.useState({ pageIndex: 0, pageSize })`; `onPaginationChange: setPagination` | `components/common/PanelDataGrid.tsx:185-188,254` |
| Rows-per-page selector calls `table.options.onPaginationChange` | `components/ui/data-grid-pagination.tsx:165-174`, sizes `[25, 50, 100]` at `:36` |
| Column-config store: `user_list_column_configs.config` JSONB, one row per user per listing key | model `app/models/user.py:699-724` |
| Payload fields today: `version, columnOrder, columnVisibility, columnSizing, sorting, filters, filtersVersion, defaultSavedViewId`; PUT is a PARTIAL merge (`exclude_unset`) | BE `app/schemas/list_query.py:156-186`, route `app/api/v1/list_query.py:274`; FE `lib/listing-column-preferences/listColumnPreferencesService.ts:18-39` |
| `DataGrid` wires `useListingColumnPreferences({ table, listingKey })` for every grid with a key (pathname fallback; `null` opts out) | `components/ui/data-grid.tsx:395-405` |
| That hook loads the row once, applies `columnOrder/columnVisibility/columnSizing` to the table, and debounce-saves those three on change | `lib/listing-column-preferences/useListingColumnPreferences.ts` |
| No `pageSize`/`limit` anywhere in the store or in `localStorage`; a server-paginated list's page size lives in its own `useState<PaginationState>` (e.g. `SalesOrdersGrid.tsx:259`), restored from the detail-URL round trip via `useListStateFromUrl`/`parseDetailSearch` (N4, review round 1: the original row here wrongly attributed this to `hooks/useListPager.ts`, which is prev/next record navigation over the React Query cache, not a list's own pagination state) | grep, 22-23 Sep |
| Board list sort is local state too; owner ruled NOT to persist it (R2): the default order stays | `PanelDataGrid.tsx:190` |

## Rulings (owner, 22 Sep 2026)

- R1 Page size memory for EVERY listing that carries a `listingKey` (the board list is one
  of them), through the same store column order already uses. Not a board-only patch.
- R2 Sort is NOT persisted on the board list. Default order (AutoCount line sequence)
  stays on every open. Out of scope here.
- R3 (review round 1, 23 Sep 2026, captain ruling on reviewer findings): `pageSize` is a
  BOUNDED INT, not a fixed list of 25/50/100. ~45 listings default their own Rows-per-page
  menu to sizes outside that set (10/15/20: `roles/role-list.tsx:57`,
  `ReorderPolicyGrid.tsx:61`, `CollectionsList.tsx:72`, `PickingLinesList.tsx:36`,
  `ReportPage.tsx:263`; `OrderInquiryLinesTab.tsx:117` offers `[10, 25, 50]`), and a fixed
  `Literal[25, 50, 100]` 422s every one of them the moment they open, which fails R1 for
  those listings. The bound is `MAX_LIST_PAGE_SIZE` (100, `lib/listNavQuery.ts`), the same
  number that already caps a hand-edited detail-URL page.

## Design (one seam)

`useListingColumnPreferences` learns one more key, `pageSize`, next to the three column
keys it already owns. The TanStack `table` it is handed already exposes
`getState().pagination.pageSize` and `setPageSize()`, so the hook is the one place that
sees every grid, client-paginated (`PanelDataGrid`) and server-paginated alike.

1. Schema (R3, review round 1): `pageSize: Optional[int] = Field(default=None, ge=1,
   le=100)` on the BE `UserListColumnConfigPayload` - a BOUNDED INT, not a fixed list.
   `pageSize?: number | null` on the FE type. The FE hook validates a saved value against
   the SAME predicate on read that the BE enforces on write (`Number.isInteger(n) && n >=
   1 && n <= MAX_LIST_PAGE_SIZE`, `lib/listNavQuery.ts`) - not `components/ui`'s
   `DEFAULT_PAGE_SIZES`, which would invert the `lib -> components/ui` layering and
   reopen the import cycle `useListingColumnPreferences.ts -> data-grid-pagination.tsx ->
   data-grid.tsx -> useListingColumnPreferences.ts`. The BE bound only guards the WRITE;
   a value saved before the bound existed can still survive a GET, so the FE drops it on
   read with the same predicate.
2. Apply: when the config arrives and carries a valid `pageSize` that differs from the
   table's current one, the hook calls `table.setPagination({ pageIndex: 0, pageSize:
   saved })`. TanStack's `setPageSize` alone does NOT reset `pageIndex` - it keeps the
   TOP ROW visible (`old.pageSize * old.pageIndex / newPageSize`) - so `setPagination`
   is what actually lands on page 1 of the new size, which is right: a different size
   means a different page boundary.
3. Save: the hook watches `table.getState().pagination.pageSize`; a change after the
   config has loaded goes through its OWN debounced PUT (a separate `debounce` instance
   from the column keys' - review round 1 B1: sharing one meant a change inside the same
   window as a column change silently dropped whichever call came first, since `debounce`
   only remembers its latest call) as `{ pageSize }` (partial merge, so the other keys are
   untouched).
4. `resetToDefaults` (the column menu's "Reset to defaults") DELETEs the row, which
   already clears `pageSize` with it; the hook then puts the grid back to the caller's
   own default size via the same `setPagination({ pageIndex: 0, pageSize })` call - read
   once at mount, the same way `defaultOrder` is.
5. `suppressPersist` (saved-view apply) suppresses this key too, same guard, same reason.
6. The "no saved row yet" branch (payload `null`) seeds BOTH `persistedPageSizeRef` and
   the column fingerprint ref to the table's own mount-time defaults (review round 1 B2):
   leaving either at its initial `null` reads as "the server holds something different
   from what's on screen" and writes a row on the listing's very first open, before any
   user action.

No change to `PanelDataGrid`, `FulfilmentBoardListView`, `DataGridPagination` or any
listing page. A server-paginated list's own `pageSize` (its `useState<PaginationState>`,
not `hooks/useListPager.ts` - see the measured-facts row) gets the saved size applied
through its own `onPaginationChange`, which refetches with the new `limit`: the first
open of such a list may fetch page 1 at 25 and again at the saved size while the config
query is in flight. Accepted; the config query is cached per key after that.

## Not in scope

- Sort persistence on the board list (R2).
- Persisting `pageIndex` (which page): a reopen starts on page 1, as today.
- `listingKey={null}` grids (the stock-debt calendar) stay unpersisted, page size included.

## Tests

vitest, `lib/listing-column-preferences/useListingColumnPreferences.test.tsx` (extend):

- Red 1: config `{ pageSize: 50 }` arrives, table starts on page 3 -> `setPagination`
  lands it on `pageSize` 50, `pageIndex` 0 (a real assertion, not a coincidence of
  already being on page 0), called once, and nothing is written back immediately.
- Red 2: config with a `pageSize` past the bound (review round 1: 500, since 33 became a
  VALID size once the bound replaced the fixed list) -> nothing applied, table stays at
  its default.
- Red 3: user changes size 25 -> 100 after load -> one debounced PUT whose body carries
  `pageSize: 100` and no column keys it did not change.
- Red 4: a size change BEFORE the config has loaded (GET still in flight) is not saved.
- B4 (review round 1, kill test): a size change is still not saved once the GET has
  SETTLED (rejected) but never applied anything - a case Red 4 alone does not cover,
  since there `isFetching` was still doing the guarding.
- B2 (review round 1, blocker): opening a listing with no saved row (`config: null`)
  writes nothing on its own - covers BOTH writers this hook owns (`persistedPageSizeRef`
  and the column fingerprint ref), not just the page-size one.
- S2 (review round 1): a saved row carrying ONLY a valid `pageSize` (no column keys)
  still flips `isLoading` false - the `applied` state twin this round's own Red 2 (round
  1) exposed a gap in.
- B1 (review round 1, blocker): a column change and a page-size change inside the same
  debounce window both write, neither losing the other's payload key.
- Red 5: `resetToDefaults` -> DELETE, then table back at the mount-time default size
  (page 0), and nothing further is written.
- Red 6: `suppressPersist: true` -> a size change writes nothing.

pytest, `tests/test_list_column_preferences.py` (extended the file that already covers
PUT merge, per the coder's grep for `column-config` under `tests/`):

- Red 7: PUT `{ "pageSize": 50 }` merges into an existing row that carries `columnOrder`,
  `sorting`, `filters` and `defaultSavedViewId`; GET returns all of them (review round 1:
  the merge assertion covered only `columnOrder`, not the OTHER writer's keys).
- Red 8 (review round 1: bounded int, not a fixed list): PUT `{ "pageSize": 0 }` and
  `{ "pageSize": 101 }` (`MAX_LIST_PAGE_SIZE` + 1) are both refused 422 and write
  nothing; `{ "pageSize": 10 }` - one of the sizes the ~45 non-25/50/100 listings
  actually use - is accepted.

## Verification

Browser (agent-browser, via sidebar from `/`): open the fulfilment planning board for one
order, List view, set rows per page to 100, navigate away, come back through the sidebar:
100 is selected and 100 rows show. Reset to defaults from the column menu: 25 again. Second
listing (Sales Orders list) same round trip at 50, to prove R1.

## Guide

One sentence in the listing personalisation guide, next to the column order sentence:
rows per page is remembered per list.
