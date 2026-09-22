# UAC: rows-per-page is remembered per user per listing

Plan: `PLAN-listing-page-size-memory.md`
Owner ruling: 22 Sep 2026 (R1 every listing with a key, R2 no sort persistence)
Review round 1 ruling, 23 Sep 2026: `pageSize` is a BOUNDED INT (1..`MAX_LIST_PAGE_SIZE`,
100, `lib/listNavQuery.ts`), not a fixed list of 25/50/100 - ~45 listings default their own
Rows-per-page menu outside those three sizes (10/15/20, or add 10 to the usual set), and a
fixed list 422s every one of them on open, which fails R1.

## Store

- AC-1 `UserListColumnConfigPayload` (BE and FE) carries `pageSize`, optional, a bounded int
  from 1 to `MAX_LIST_PAGE_SIZE` (100). PUT `/api/v1/list-query/column-config/{listing_key}`
  with `{ "pageSize": 50 }` merges into the existing row and leaves `columnOrder`,
  `columnVisibility`, `columnSizing`, `sorting`, `filters`, `defaultSavedViewId` untouched.
  GET returns it.
- AC-2 PUT with a `pageSize` of 0 or above `MAX_LIST_PAGE_SIZE` answers 422 and writes
  nothing; any size in between (10, for the listings that use it, included) is accepted.
- AC-3 DELETE (reset to defaults) removes the row, `pageSize` with it.

## Apply

- AC-4 A grid with a `listingKey` whose saved config carries `pageSize: 50` opens on 50
  rows per page, page 1, and the rows-per-page selector reads 50.
- AC-5 A saved `pageSize` outside the bound (0, or above `MAX_LIST_PAGE_SIZE`) is ignored:
  the grid opens on its own default (the caller's `pageSize` prop, 25 on the board list).
  This can only happen from a row written before the bound existed or from a restore - the
  BE bound already refuses it on write (AC-2).
- AC-6 A grid with `listingKey={null}` never reads or writes `pageSize`.

## Save

- AC-7 Changing rows per page after the config has loaded writes ONE debounced PUT carrying
  `pageSize` and nothing else the user did not change.
- AC-8 A change made before the config has loaded is not written.
- AC-9 With `suppressPersist` on (a saved view applying), a size change writes nothing.
- AC-10 "Reset to defaults" in the column menu returns the grid to its mount-time default
  size in the same action that resets the columns.

## Board list (owner's screen)

- AC-11 Fulfilment planning board, List view, "Every contributing line": pick 100, leave the
  page through the sidebar, come back to the same board: 100 selected, up to 100 rows shown.
- AC-12 The list's row ORDER on reopen is the default order (R2). Sorting a column and
  reopening does not bring the sort back.
- AC-13 A second listing (Sales Orders list) remembers 50 the same way, and the two lists'
  sizes are independent of each other.

## Not changed

- AC-14 `PanelDataGrid`'s keep-page behaviour across a save (PLAN-panel-datagrid-keep-page)
  still holds: a draft save on page 3 at 50 rows stays on page 3.
- AC-15 Page index is not remembered: a reopen starts on page 1.
