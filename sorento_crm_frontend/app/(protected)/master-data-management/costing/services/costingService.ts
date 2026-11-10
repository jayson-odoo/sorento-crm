/**
 * Products > Costing - feature service (lane PRODUCT-COSTING).
 *
 * Layering: components -> hooks (useCosting) -> THIS service -> lib/api.
 *
 * Backend (module `master_data`, `/api/v1/master-data/costing`, CONTRACT-product-costing.md s4):
 *   GET   /rows                              -> CostingRowsResponse          products.cost.view
 *   PATCH /rows            body SaveRowsBody -> { updated }                  + products.party_costing.manage
 *   GET   /rows/{product}/suppliers          -> { data: SupplierBreakdown[] }
 *   GET   /rows/{product}/history?party_id   -> { data: HistoryEntry[] }
 *   GET   /export                            -> .xlsx
 *   GET|PUT /settings                        -> CostingSettings
 *   GET   /category-rules, PUT /category-rules/{category}
 *   GET|POST /exchange-rates, PUT /exchange-rates/{id}                       scm.config.manage to write
 *   GET|PUT /parties/{customer}, POST /parties/{customer}/products
 * Removing a product from a party (costing_party_product.unlink) and deleting a rate
 * (exchange_rate.delete) are deferred pending actions, never a call from here (D7).
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import { filenameFromContentDisposition, saveBlobAs } from '@/lib/save-blob';
import type {
  CategoryRule,
  CostingParty,
  CostingRowsParams,
  CostingRowsResponse,
  CostingSettings,
  CostingSupplierParams,
  ExchangeRate,
  ExchangeRateBody,
  HistoryEntry,
  PartyBody,
  SaveRowsBody,
  SupplierBreakdown,
} from '../types/costing.types';

const BASE = '/api/v1/master-data/costing';

async function read<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) throw new Error(await extractApiError(response, fallback));
  return response.json();
}

function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
}

/** The query string for the rows and export reads: absent keys stay out, has_cost only when true. */
export function costingQuery(params: CostingRowsParams | CostingSupplierParams): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '' || value === false) continue;
    search.set(key, value === true ? 'true' : String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}

export async function getCostingRows(params: CostingRowsParams, signal?: AbortSignal): Promise<CostingRowsResponse> {
  const url = `${BASE}/rows${costingQuery(params)}`;
  return read(await (signal ? apiFetch(url, { signal }) : apiFetch(url)), 'Failed to load costing');
}

export async function getCostingRowSuppliers(
  productId: string,
  params: CostingSupplierParams,
): Promise<{ data: SupplierBreakdown[] }> {
  return read(
    await apiFetch(`${BASE}/rows/${encodeURIComponent(productId)}/suppliers${costingQuery(params)}`),
    'Failed to load the suppliers',
  );
}

export async function saveCostingRows(body: SaveRowsBody): Promise<{ updated: number }> {
  return read(await apiFetch(`${BASE}/rows`, jsonInit('PATCH', body)), 'Failed to save costing');
}

export async function getCostingRowHistory(
  productId: string,
  partyId?: string | null,
): Promise<{ data: HistoryEntry[] }> {
  const query = costingQuery(partyId ? { party_id: partyId } : {});
  return read(
    await apiFetch(`${BASE}/rows/${encodeURIComponent(productId)}/history${query}`),
    'Failed to load the history',
  );
}

/** Download the filtered set as .xlsx (the same query as the rows, without paging). */
export async function exportCosting(params: CostingRowsParams): Promise<void> {
  // The export is the whole filtered set: never one page of it.
  const response = await apiFetch(`${BASE}/export${costingQuery({ ...params, page: undefined, limit: undefined })}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to export costing'));
  const name =
    filenameFromContentDisposition(response.headers.get('Content-Disposition')) ?? 'costing.xlsx';
  saveBlobAs(await response.blob(), name);
}

export async function getCostingSettings(): Promise<CostingSettings> {
  return read(await apiFetch(`${BASE}/settings`), 'Failed to load the settings');
}

export async function saveCostingSettings(body: CostingSettings): Promise<CostingSettings> {
  return read(await apiFetch(`${BASE}/settings`, jsonInit('PUT', body)), 'Failed to save the settings');
}

export async function getCategoryRules(): Promise<{ data: CategoryRule[] }> {
  return read(await apiFetch(`${BASE}/category-rules`), 'Failed to load the transport rules');
}

export async function saveCategoryRule(
  categoryId: string,
  body: { mode: string | null; value: number | null },
): Promise<{ category_id: string; mode: string | null; value: number | null }> {
  return read(
    await apiFetch(`${BASE}/category-rules/${encodeURIComponent(categoryId)}`, jsonInit('PUT', body)),
    'Failed to save the transport rule',
  );
}

export async function getExchangeRates(currency?: string): Promise<{ data: ExchangeRate[] }> {
  const query = currency ? `?currency=${encodeURIComponent(currency)}` : '';
  return read(await apiFetch(`${BASE}/exchange-rates${query}`), 'Failed to load the exchange rates');
}

export async function createExchangeRate(body: ExchangeRateBody): Promise<ExchangeRate> {
  return read(await apiFetch(`${BASE}/exchange-rates`, jsonInit('POST', body)), 'Failed to add the rate');
}

export async function updateExchangeRate(id: string, body: ExchangeRateBody): Promise<ExchangeRate> {
  return read(
    await apiFetch(`${BASE}/exchange-rates/${encodeURIComponent(id)}`, jsonInit('PUT', body)),
    'Failed to save the rate',
  );
}

export async function getParty(customerId: string): Promise<CostingParty> {
  return read(await apiFetch(`${BASE}/parties/${encodeURIComponent(customerId)}`), 'Failed to load the party');
}

export async function saveParty(customerId: string, body: PartyBody): Promise<CostingParty> {
  return read(
    await apiFetch(`${BASE}/parties/${encodeURIComponent(customerId)}`, jsonInit('PUT', body)),
    'Failed to save the party',
  );
}

export async function addPartyProducts(
  customerId: string,
  productIds: string[],
): Promise<{ added: number; already: number }> {
  return read(
    await apiFetch(
      `${BASE}/parties/${encodeURIComponent(customerId)}/products`,
      jsonInit('POST', { product_ids: productIds }),
    ),
    'Failed to add the products',
  );
}
