# DataGrid Standardization Guide

This project now has a reusable toolbar foundation for table pages:

- `Export`
- `Advanced filters`
- `Columns`

Use `DataGridStandardToolbar` in `CardHeader` for every list built on `DataGrid`.

## Shared building blocks

- `components/ui/data-grid-standard-toolbar.tsx`
 - Generic mode:
  - Advanced filters via popover content.
  - Export current table rows to Excel.
  - Column visibility via existing `DataGridColumnVisibility`.
 - List-query mode:
  - Reuses `ListQueryFilterDialog`.
  - Reuses `ListQueryExportDialog`.
  - Falls back to generic mode for non-list-query resources.

## Standard page structure

For top-level list pages, use:

1. `Container + Toolbar + Breadcrumb` (page shell)
2. `Container + DataGrid + Card`
3. `CardHeader` includes `DataGridStandardToolbar`
4. `CardTable` includes `DataGridTable`
5. `CardFooter` includes `DataGridPagination`

## Migration pattern for DataGrid pages

1. Replace custom column-visibility button with `DataGridStandardToolbar`.
2. Move existing quick filters/search into:
 - `searchSlot`
 - `quickFiltersSlot`
3. Move custom actions into:
 - `secondaryActionsSlot` (bulk delete/import)
 - `primaryActionsSlot` (create action)
4. Add `advancedFilters` config:
 - `active`: whether filter badge should show
 - `content`: filter form JSX
5. Add export config:
 - `exportConfig.filename` for generic export
 - or `listQueryConfig` for list-query-backed export/filter dialogs

## Implemented in Phase 1

- `app/(protected)/procurement-management/grn/components/GRNList.tsx`
- `app/(protected)/inventory-management/stock-ledger/components/StockLedgerList.tsx`
- `app/(protected)/sla-management/escalation-logs/components/EventLogList.tsx`
- `app/(protected)/sla-management/conversation-sla-tracking/components/EventLogTable.tsx`
- Page shell normalization:
 - `app/(protected)/inventory-management/stock-ledger/page.tsx`
 - `app/(protected)/sla-management/escalation-logs/page.tsx`

## Non-DataGrid tables (separate migration)

These are not automatic and require separate conversion to `DataGrid` if standard controls are needed:

- Detail tables and embedded line-item tables using `components/ui/table` (examples: packing list detail, purchase request detail, GRN detail, order lines card, attachment/detail panels).
- Once migrated to `DataGrid`, the standard toolbar can be applied with minimal extra wiring.
