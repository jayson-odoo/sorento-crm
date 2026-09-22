# PLAN: rows-per-page is remembered per user per listing, like column order

Status: implemented, awaiting review (22 Sep 2026). Track: small fix.
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
| No `pageSize`/`limit` anywhere in the store or in `localStorage`; server-paginated lists carry `limit` in the URL only (`hooks/useListPager.ts`) | grep, 22 Sep |
| Board list sort is local state too; owner ruled NOT to persist it (R2): the default order stays | `PanelDataGrid.tsx:190` |

## Rulings (owner, 22 Sep 2026)

- R1 Page size memory for EVERY listing that carries a `listingKey` (the board list is one
  of them), through the same store column order already uses. Not a board-only patch.
- R2 Sort is NOT persisted on the board list. Default order (AutoCount line sequence)
  stays on every open. Out of scope here.

## Design (one seam)

`useListingColumnPreferences` learns one more key, `pageSize`, next to the three column
keys it already owns. The TanStack `table` it is handed already exposes
`getState().pagination.pageSize` and `setPageSize()`, so the hook is the one place that
sees every grid, client-paginated (`PanelDataGrid`) and server-paginated alike.

1. Schema: `pageSize: Optional[int] = None` on the BE `UserListColumnConfigPayload`;
   `pageSize?: number | null` on the FE type. Validated to one of `25 | 50 | 100`
   (`DEFAULT_PAGE_SIZES`); anything else is dropped on read, never applied.
2. Apply: when the config arrives and carries a valid `pageSize` that differs from the
   table's current one, the hook calls `table.setPageSize(saved)`. TanStack resets
   `pageIndex` to 0 on that call, which is right: a different size means a different page
   boundary.
3. Save: the hook watches `table.getState().pagination.pageSize`; a change after the
   config has loaded goes through the same debounced PUT as the column keys, as
   `{ pageSize }` (partial merge, so the other keys are untouched).
4. `resetToDefaults` (the column menu's "Reset to defaults") DELETEs the row, which
   already clears `pageSize` with it; the hook then puts the grid back to the caller's
   own default size (the `pageSize` prop `PanelDataGrid` was given, or the
   `useListPager` default) - read once at mount, the same way `defaultOrder` is.
5. `suppressPersist` (saved-view apply) suppresses this key too, same guard, same reason.

No change to `PanelDataGrid`, `FulfilmentBoardListView`, `DataGridPagination` or any
listing page. Server-paginated lists whose `pageSize` lives in `useListPager` state get
the saved size applied through their own `onPaginationChange`, which refetches with the
new `limit`: the first open of such a list may fetch page 1 at 25 and again at the saved
size while the config query is in flight. Accepted; the config query is cached per key
after that.

## Not in scope

- Sort persistence on the board list (R2).
- Persisting `pageIndex` (which page): a reopen starts on page 1, as today.
- `listingKey={null}` grids (the stock-debt calendar) stay unpersisted, page size included.

## Tests

vitest, `lib/listing-column-preferences/useListingColumnPreferences.test.tsx` (extend):

- Red 1: config `{ pageSize: 50 }` arrives, table at 25 -> `setPageSize(50)` called once,
  `pageIndex` 0.
- Red 2: config with `pageSize: 33` (not a listed size) -> nothing applied, table stays at
  its default.
- Red 3: user changes size 25 -> 100 after load -> one debounced PUT whose body carries
  `pageSize: 100` and no column keys it did not change.
- Red 4: a size change BEFORE the config has loaded is not saved (same rule as columns).
- Red 5: `resetToDefaults` -> DELETE, then table back at the mount-time default size.
- Red 6: `suppressPersist: true` -> a size change writes nothing.

pytest, `tests/test_list_query_column_config.py` (new, or extend the file that already
covers PUT merge if one exists - coder greps `column-config` under `tests/`):

- Red 7: PUT `{ "pageSize": 50 }` merges into an existing row with `columnOrder`, GET
  returns both.
- Red 8: PUT `{ "pageSize": 33 }` is refused 422 (Literal validation).

## Verification

Browser (agent-browser, via sidebar from `/`): open the fulfilment planning board for one
order, List view, set rows per page to 100, navigate away, come back through the sidebar:
100 is selected and 100 rows show. Reset to defaults from the column menu: 25 again. Second
listing (Sales Orders list) same round trip at 50, to prove R1.

## Guide

One sentence in the listing personalisation guide, next to the column order sentence:
rows per page is remembered per list.
