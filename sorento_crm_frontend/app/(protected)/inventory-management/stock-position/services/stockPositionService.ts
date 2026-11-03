import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError, type DataGridParamsInput } from '@/lib/api-client';
import { joinMulti } from '@/lib/list-filters/multiValue';
import { saveBlobAs } from '@/lib/save-blob';
import type { StockPositionFilters, StockPositionResponse } from './stockPosition.types';

const BASE = '/api/v1/inventory/stock-position';

/** Ids comma-joined in one param per filter; an empty selection leaves the param out. */
function filterParams(filters: StockPositionFilters) {
  return {
    supplier_id: joinMulti(filters.supplierIds ?? []) || undefined,
    brand_id: joinMulti(filters.brandIds ?? []) || undefined,
    warehouse_id: joinMulti(filters.warehouseIds ?? []) || undefined,
  };
}

/** The query string: DataGrid params, the filters that are set, one `hide` per hidden total-part column. */
function searchFor(params: DataGridParamsInput, filters: StockPositionFilters) {
  const search = buildDataGridParams(params, filterParams(filters));
  for (const id of filters.hiddenColumns ?? []) search.append('hide', id);
  return search;
}

/** One page, sorted and filtered on the server. */
export async function getStockPosition(
  params: DataGridParamsInput,
  filters: StockPositionFilters,
): Promise<StockPositionResponse> {
  const response = await apiFetch(`${BASE}?${searchFor(params, filters).toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load the stock position'));
  return response.json();
}

/**
 * Every row of the same filtered, sorted set, as the server's Excel workbook: the warehouse columns
 * the user shows and the totals over them (`filters.hiddenColumns`, the same set the grid sends).
 */
export async function exportStockPosition(params: DataGridParamsInput, filters: StockPositionFilters): Promise<void> {
  const search = searchFor(params, filters);
  search.delete('page');
  search.delete('limit');
  const response = await apiFetch(`${BASE}/export?${search.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to export the stock position'));
  saveBlobAs(await response.blob(), 'stock-position.xlsx');
}
