# PLAN: DataGrid drag / range select (GRID-DRAG-SELECT)

Status: Plan (behaviour card + interactive mock posted as crew-ask on the PR, waiting on owner answers). Track: small fix track (FE only, no migration, no RBAC change).

## Journey

Owner, 27 Oct: ticking many rows in a list (Contacts, bulk Actions bar) means clicking every
checkbox one by one. Wants to sweep a run of rows in one gesture without breaking text selection
for copy.

## Scout (main @ 79821711)

- Two row-checkbox paths:
  - `buildSelectColumn` in `sorento_crm_frontend/components/ui/data-grid-select-column.tsx:18`
    (cell at :67, header at :45). Used by 95 list files (Contacts, Sales orders, Orders, ...).
  - `DataGridTableRowSelect` in `sorento_crm_frontend/components/ui/data-grid-table.tsx:1141`
    (46 more usages). Stops click + pointerdown propagation so the row never opens from it.
- Selection state is react-table `rowSelection`, keyed by `getRowId` (Contacts:
  `ContactsList.tsx:761`), so ticks survive page changes; Contacts resets it when filters change
  (`ContactsList.tsx:785`).
- Row open: `rowOpenProps` (`data-grid-table.tsx:557`) ignores clicks whose target matches
  `ROW_INTERACTIVE_SELECTOR` (`:533`, includes `[role="checkbox"]`). Text selection is untouched
  by the grid today.
- Header checkbox: page scope by default, `selectAllRows` opt-in for all loaded rows
  (`data-grid-select-column.tsx:45-63`).
- "Select all N records" banner already exists in the toolbar
  (`data-grid-list-toolbar.tsx:646-668`, prop `selectAllMatching` at :225) but only 2 grids pass it:
  `StockBalanceGrid.tsx` and `OrderInquiriesClient.tsx` (its bulk endpoint accepts a filter,
  :1317). Contacts bulk actions post id lists; the contacts list endpoint allows `limit<=1000`
  (`sorento_crm_backend/app/api/v1/user_management/contacts.py:93`).
- Page sizes: 25 / 50 / 100 (`components/ui/data-grid-pagination.tsx:36`).

## Options (mock: `mock-grid-drag-select.html` beside this file)

- A. Shift+click a checkbox: range from the last clicked box takes that box's state.
- B. Press on the checkbox column and drag up/down: first box decides tick or untick; dragging
  back restores the rows' earlier state. Mouse/pen only; touch keeps scrolling.
- C. Select all N matching (Contacts): fetch matching ids, capped at 1000, tick them.
- D. Keyboard: roving focus on checkbox column, Space toggles, Shift+Up/Down extends.

## Implementation sketch (after owner answers)

One hook `useRangeSelection(table)` in `components/ui/` shared by both checkbox paths, holding the
anchor row id and the drag session (pointer events on the select cell, `user-select:none` on the
document only while a drag is live, window pointerup/cancel ends it). Tests red-first in
`data-grid-select-column.test.tsx` + a new `data-grid-range-select.test.tsx`.
