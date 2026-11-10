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
- This deliberately reverses f6c153453's "the menu must not re-sort after a drag" choice: a
  stable list is exactly what read as "ticked but not shown". Its other point, grouped columns'
  members stay reachable, still holds (`getAllLeafColumns()` flattens groups). The menu cannot
  be open during a drag, and hiding a column keeps its slot, so the list never shifts under the
  reader's pointer.
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

## Browser evidence run (cloud sandbox, agent-browser 0.27.0, 10 Nov)

Stack: backend on the sandbox `sorento_ci` DB (bootstrap seed, `scripts.seed_never_stuck_smoke`
admin), `next dev` on :3000. The owner's saved row above was PUT to
`/api/v1/list-query/column-config/%2Fmaster-data-management%2Fproducts` for that admin.

1. Sign in, sidebar Products > Products > All Products (`/master-data-management/products`).
2. Grid headers: Product Code, Product Name, Category, Brand, Item Class, List Price, List price
   changed at, Status, Created, Updated, Type, Variant of, Variants, Discontinued, Discontinued
   at, Chat Search (same as the owner's screen: the variant columns past Updated).
3. main: the Columns menu read Type, Variant of, Variants, Category, ... (definition order), the
   owner's mismatch (`columns-toggle-truth-before.png`).
4. This branch: the menu reads Category, Brand, Item Class, List Price, List price changed at,
   Status, Created, Updated, Type, Variant of, Variants, Discontinued, Discontinued at, Chat
   Search (all ticked), Reorder Planning (unticked) - the grid's order exactly
   (`columns-toggle-truth-after.png`).
5. Untick Type: the grid drops Type, the menu shows it unticked in the same slot; re-tick restores.

## Other lists checked

Every DataGrid list reaches the toolbar menu through `DataGridListToolbar` or one of the 28
direct `DataGridColumnVisibility` call sites, so they all had the same definition-order menu and
all get this fix. A list shows the mismatch only when the reader's saved order differs from the
definition order (a drag, a Move Left/Right, or a pre-17-Aug saved row that got new columns
appended). The header dropdown's Columns submenu (not mounted today) now shares the same items.
