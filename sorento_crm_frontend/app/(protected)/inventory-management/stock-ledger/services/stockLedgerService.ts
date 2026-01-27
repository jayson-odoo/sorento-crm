import { apiFetch } from '@/lib/api';
import type { StockLedgerEntry } from '../types/stockLedger.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getStockLedger(
  params: DataGridApiFetchParams & { product_id?: string; warehouse_id?: string; transaction_type?: string },
): Promise<DataGridApiResponse<StockLedgerEntry>> {
  const { pageIndex, pageSize, sorting, product_id, warehouse_id, transaction_type } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(product_id ? { product_id } : {}),
    ...(warehouse_id ? { warehouse_id } : {}),
    ...(transaction_type ? { transaction_type } : {}),
  });
  const response = await apiFetch(`/api/v1/inventory/stock-ledger?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch stock ledger');
  return response.json();
}
