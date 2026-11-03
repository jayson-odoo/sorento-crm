# PLAN: Stock position Supplier, Brand, Warehouse filters multi-select (STOCKPOS-FILTER-MULTI)

Status: Review (reviewer READY 3 Nov, should-fix items folded in; owner hand test next). Small fix track (expected diff under 300 lines, no migration, no auth/RBAC change,
no new ingest surface).

## Why

Owner rule 27 Oct (FILTER-MULTISELECT, `documentation/plans/ui/PLAN-filter-multiselect.md`): every
dropdown filter is multi-select. Crew browser pass on #2109 (3 Nov) found Inventory > Stock position
still single-select for Supplier, Brand and Warehouse: a second Brand pick replaces the first.

## Filters on the screen (all checked)

| Filter | Today | Change |
|---|---|---|
| Search (item code / description) | free text | none (rule 1: free text stays) |
| Supplier | single, async `SearchableSelect` | `SearchableMultiSelect` async |
| Brand | single `SearchableSelect` | `SearchableMultiSelect` |
| Warehouse | single `SearchableSelect` | `SearchableMultiSelect` |

## Shape (the shared FILTER-MULTISELECT parts, no new machinery)

- FE control: `components/common/SearchableMultiSelect.tsx`; values helpers
  `lib/list-filters/multiValue.ts` (`splitMulti`/`joinMulti`/`multiChipLabel`/`idFilterLabels`),
  same as `CostPriceUploadsList.tsx` (async supplier multi).
- Wire: ids comma-joined in one param (`brand_id=a,b`).
- BE: `app/api/v1/inventory/stock_position.py` passes each param through
  `app/utils/multi_value.py` `multi_values`, so comma-joined, repeated and single values read alike
  (today a comma-joined value is read as ONE id and matches nothing). Service already filters by set
  membership (IN) before sort and paging, so the page total and the export follow the selection.
- Persistence: the list state rides the page URL (`buildDetailSearch`) and is restored by
  `useListStateFromUrl`, so Back from Stock status returns to the same filtered view.
- Out of scope: #2109 dynamic total (STOCK-POS-DYNAMIC-TOTAL).

## Tests (red first)

- BE `tests/scm/test_stock_position.py::test_supplier_brand_and_warehouse_filters_take_several_values_or_ed`.
- FE `services/stockPositionService.test.ts` (comma-joined params, export too) and
  `components/StockPositionGrid.multiFilters.test.tsx` (a second Brand pick adds, not replaces;
  export and URL carry the selection; the list's own URL write never re-applies over typing).
