import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError, type DataGridParamsInput } from '@/lib/api-client';
import { saveBlobAs } from '@/lib/save-blob';
import type { StockPositionFilters, StockPositionResponse } from './stockPosition.types';

const BASE = '/api/v1/inventory/stock-position';

function filterParams(filters: StockPositionFilters) {
  return {
    supplier_id: filters.supplierId,
    brand_id: filters.brandId,
    warehouse_id: filters.warehouseId,
  };
}

/** One page, sorted and filtered on the server. */
export async function getStockPosition(
  params: DataGridParamsInput,
  filters: StockPositionFilters,
): Promise<StockPositionResponse> {
  const search = buildDataGridParams(params, filterParams(filters));
  const response = await apiFetch(`${BASE}?${search.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load the stock position'));
  return response.json();
}

/**
 * Every row of the same filtered, sorted set, as the server's Excel workbook, with the warehouse
 * columns the user shows (`warehouseCodes`; every one when omitted).
 */
export async function exportStockPosition(
  params: DataGridParamsInput,
  filters: StockPositionFilters,
  warehouseCodes?: string[],
): Promise<void> {
  const search = buildDataGridParams(params, filterParams(filters));
  search.delete('page');
  search.delete('limit');
  if (warehouseCodes) {
    // Every warehouse hidden is "none", not "all": an empty code matches no column.
    for (const code of warehouseCodes.length ? warehouseCodes : ['']) search.append('wh', code);
  }
  const response = await apiFetch(`${BASE}/export?${search.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to export the stock position'));
  saveBlobAs(await response.blob(), 'stock-position.xlsx');
}
