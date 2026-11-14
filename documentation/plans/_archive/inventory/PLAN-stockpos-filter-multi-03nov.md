# PLAN: Stock position Supplier, Brand, Warehouse filters multi-select (STOCKPOS-FILTER-MULTI)

Status: Implemented. #2130 merged 3 Nov (owner hand test OK, crew browser pass GO); follow-up
PR (STOCKPOS-FILTER-MULTI round 2) names every chosen supplier and uses Stock's trigger format.
Small fix track.

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

## Round 2 (crew browser pass, 3 Nov)

- A chosen supplier on no row of the page and never in the picker's pages read "Selected supplier":
  `hooks/useSupplierNames.ts` looks its name up by id (`getSupplier`, cache key `['supplier', id]`
  shared with `useSupplier`; same `get_current_user` gate as the picker's `/select`).
- Trigger labels use Stock's format (`StockBalanceGrid.tsx`): `Warehouse: BRW, DC1`, `Warehouse: any`.
- Tests: `StockPositionGrid.multiFilters.test.tsx` (both red on the #2130 code first).
