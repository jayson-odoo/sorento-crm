import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { StockStatus } from './stockStatus.types';

const BASE = '/api/v1/inventory/stock-status';

/** One item, every location, with its documents. `soDueBy` (YYYY-MM-DD) cuts SO only. */
export async function getStockStatus(productId: string, soDueBy: string | null): Promise<StockStatus> {
  const search = new URLSearchParams({ product_id: productId });
  if (soDueBy) search.set('so_due_by', soDueBy);
  const response = await apiFetch(`${BASE}?${search.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load the stock status'));
  return response.json();
}

export interface StockStatusProductOption {
  value: string;
  label: string;
  description?: string;
  searchText?: string;
}

/**
 * The stand-alone page's item picker: products searched on the server, one page at a time
 * (never a capped static list). Keyed by id, the code as the label and the name beside it as
 * its own field (never one joined code and name label).
 */
export async function searchStockStatusProducts(query: string, pageIndex = 0): Promise<StockStatusProductOption[]> {
  const size = 50;
  const search = new URLSearchParams({ limit: String(size), offset: String(pageIndex * size) });
  if (query.trim()) search.set('query', query.trim());
  const response = await apiFetch(`/api/v1/master-data/products/select?${search.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load products'));
  const body = (await response.json()) as { data: { id: string; product_code: string; product_name: string | null }[] };
  return body.data.map((p) => ({
    value: p.id,
    label: p.product_code,
    description: p.product_name ?? undefined,
    searchText: `${p.product_code} ${p.product_name ?? ''}`,
  }));
}
