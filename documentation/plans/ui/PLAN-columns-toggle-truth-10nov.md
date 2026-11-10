# PLAN: Columns menu is the truth for every DataGrid list (COLUMNS-TOGGLE-TRUTH)

Status: built, in review (small fix track, bug; no migration, no auth/RBAC, no new ingest)

## Problem

Owner, 10 Nov: on Products > All Products the Columns menu ("Toggle Columns") ticks Type, Variant
Of and Variants, but the grid the owner sees does not show them.

## Cause (measured)

The owner's saved row (prod copy, `user_list_column_configs`, listing key
`/master-data-management/products`) has
`columnOrder = [select, product_code, product_name, category_name, brand_name, item_class,
list_price, is_active, created_at, updated_at, variant_type, variant_of, variant_child_count,
is_discontinued, discontinued_at, is_searchable, actions, exclude_from_planning]`.

- The variant columns were added on 8 Jul (8ee2b507b). At that time `mergeColumnOrder.ts` still
  APPENDED any column a saved order had never seen at the far right, and the next save persisted
  that order. The anchor-in-place merge only arrived on 17 Aug (ac6b2fc4a), too late for rows
  saved in between.
- So the grid does render Type, Variant Of and Variants, but past Updated, off-screen.
- The toolbar Columns menu listed columns in DEFINITION order
  (`components/ui/data-grid-column-visibility.tsx`, `leafColumnsInDefinitionOrder`, since
  f6c153453), so it showed them ticked at the top. The two disagree on order, not on visibility.
  TanStack's `getIsVisible()` and the rendered cells read the same state, and a jsdom replay
  confirmed the ticked set equals the rendered set.
- The column header's own "Columns" submenu (`data-grid-column-header.tsx`) had the same
  definition order (and `getAllColumns()` could not reach grouped columns). It is currently not
  mounted (`void headerControls`).
- `data-grid-columns-panel.tsx` had no importer (dead).

## Fix

- `leafColumnsInScreenOrder(table)`: left-pinned, centre (reader's order), right-pinned leaves,
  hidden columns kept in their slot. `DataGridColumnVisibilityItems` renders the checkbox rows
  from it, and both menus use it. Every DataGrid list gets the fix through the shared toolbar
  menu (`DataGridListToolbar`) and the ~28 direct `DataGridColumnVisibility` call sites.
- Deleted the dead `data-grid-columns-panel.tsx`.
- Stale keys: the apply path (`useListingColumnPreferences.ts`) already drops ids the grid does
  not have and anchors new columns in place. The menu now reads the applied state, so a stale
  row cannot diverge from the menu. Not written back to the server automatically: report grids
  with data-dependent columns would lose saved ids for columns that arrive later (see the save
  effect's own comment). The reconciled state is saved on the reader's next column change, and
  "Reset columns" restores the defaults.

## Tests

`components/ui/data-grid-column-visibility.test.tsx`: unit (definition, dragged, pinned, hidden
slot) and integration through the real DataGrid + preference hook: the owner's saved row
verbatim, the same row with stale keys and a hidden column, and a fresh user. Red on main
(6 of 7), green after.
