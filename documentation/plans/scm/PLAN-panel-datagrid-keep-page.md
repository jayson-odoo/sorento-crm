# PLAN: PanelDataGrid keeps its page and scroll across a save

Status: in review (18 Sep 2026). Track: small fix.
Owner report: fulfilment planning list view, page 2 or 3, save a decision, the grid jumps back to page 1 and the user scrolls back down to find the next line.

## Cause

`components/common/PanelDataGrid.tsx` paginates client-side with TanStack. TanStack's
`autoResetPageIndex` defaults to ON whenever `manualPagination` is off, and it fires on
every new `data` array reference. A draft save patches the board cache (new `rows` array),
a Confirm refetches it (new array again). Either way `pageIndex` snaps to 0. The list view
itself (`FulfilmentBoardListView`) never touches the page. 36 callers share the seam.

## Fix (one seam)

In `PanelDataGrid`:

1. `autoResetPageIndex: false` on `useReactTable`.
2. Render clamp: `state.pagination` is fed `{ ...pagination, pageIndex: Math.min(pagination.pageIndex, lastPageIndex) }`
   computed straight from `filtered.length` and `pagination.pageSize` at render time (0 when
   empty), so a row removal on the last page never paints an empty table for even one frame -
   an effect-only clamp would still commit one stale paint first.
3. Persisted clamp: a second, small effect writes that same clamped index back into the real
   `pagination` state once the render settles. The render clamp alone is a paint, not a write -
   `table.previousPage()`/`nextPage()` step off the real state, so without this a previous-page
   press right after a shrink computes its new page from the stale number and looks like a dead
   click.
4. The search box keeps its own explicit reset to page 0 (already there).
5. `pageResetKey?: string` prop: a caller that filters `rows` itself before handing them to
   `PanelDataGrid` (no `searchOf`) passes its own filter key here; a change resets the page the
   same way the search box's own reset does. Wired in `FulfilmentBoardListView` (its own
   `externalSearch`, overridable by its caller), `BoardCellBreakdownDialog` (the debounced lines
   search), and `FulfilmentBoardPanel` (via `FulfilmentBoardListView`'s override, `productSearch`
   joined with `kindFilter` - the kind card also narrows the list's rows, not just the search
   box).

No backend. No migration.

## Not in scope

Server-paginated DataGrids (`buildDataGridParams` listings) already hold their page in
URL/state and are untouched.

## Tests (vitest, `components/common/PanelDataGrid.keepPage.test.tsx`)

- Red 1: 60 rows, pageSize 25, go to page 3, re-render with a new array of the same 60
  rows (one cell edited). Page 3 still shown (rows 51-60).
- Red 2: same, re-render with 30 rows. Page 2 shown (rows 26-30), not an empty page 3;
  one press of the previous-page arrow then reaches page 1 (rows 1-25) - the persisted
  clamp check, since a stale real `pagination` state would make that press a dead click.
- Red 3: typing in search still returns to page 1 (existing behaviour, guards the seam) -
  uses a needle that matches every row, so only the search box's own explicit reset (not
  the row-count clamp) can be responsible.
- Red 4: a caller-supplied `pageResetKey` change resets the page to 1; a `rows` update
  under the SAME key keeps the page (`FulfilmentBoardPanel`'s kind-filter class of bug -
  a parent filters `rows` itself and hands `PanelDataGrid` no `searchOf`).

## Verification

Owner tests on their lane stack. Agent browser pass on this worktree's dev server against
the :8080 backend if a slot is free.
