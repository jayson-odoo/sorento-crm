/**
 * Cost price change sets (Lane A, S1 + S2, #1288) - service boundary.
 *
 * PHASE 2: real `apiFetch` calls against `documentation/plans/purchasing/cost-price-api-contract.md`.
 * Layering: UI -> hooks (`hooks/useCostPriceChangeSets.ts`) -> THIS service -> `lib/api` -> backend.
 *
 * Discard (`cost_price_change_set.discard`) and a cost row's delete (`product_supplier_cost.
 * delete`) are NOT here: both are deferred-action FormActions, driven by the real
 * `useDeferredAction` at the call site - the server commits them itself once the window
 * lapses, so there is nothing for this service to call.
 */

import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError, type DataGridParamsInput } from '@/lib/api-client';
import type {
  CostPriceChangeLine,
  CostPriceChangeSetCounts,
  CostPriceChangeSetListItem,
  CostPriceChangeSetDetail,
  CostPriceHistoryEvent,
  CostPriceProbeResult,
  LineDecision,
  ProductSupplierCostRow,
  SupplierCostListEntry,
  SupplierRef,
} from '../types/costPrice.types';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';

const BASE = '/api/v1/procurement/cost-price-changes';

// ---------------------------------------------------------------------------
// The verification switch (contract section 3)
// ---------------------------------------------------------------------------

export async function getCostPriceVerificationSetting(): Promise<{ enabled: boolean }> {
  const res = await apiFetch('/api/v1/user-management/settings/');
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the verification setting'));
  const body = (await res.json()) as { settings: { cost_price_verification_enabled: boolean } };
  return { enabled: Boolean(body.settings?.cost_price_verification_enabled) };
}

export async function updateCostPriceVerificationSetting(enabled: boolean): Promise<{ enabled: boolean }> {
  const res = await apiFetch('/api/v1/user-management/settings/general', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cost_price_verification_enabled: enabled }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to update the verification setting'));
  return { enabled };
}

// ---------------------------------------------------------------------------
// 1.1 probe, 1.2 upload
// ---------------------------------------------------------------------------

export async function probeCostPriceFile(file: File): Promise<CostPriceProbeResult> {
  const body = new FormData();
  body.append('file', file);
  const res = await apiFetch(`${BASE}/probe`, { method: 'POST', body });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to read the file'));
  return (await res.json()) as CostPriceProbeResult;
}

export interface UploadCostPriceFileInput {
  file: File;
  supplier: SupplierRef;
  currency: string;
  start_date: string | null;
  end_date: string | null;
}

/** 409 `open_set_exists`, thrown with the open set attached, mirroring the contract's body. */
export class OpenSetExistsError extends Error {
  open_set: { id: string; code: string };
  constructor(open_set: { id: string; code: string }) {
    super(`${open_set.code} is still open for this supplier.`);
    this.open_set = open_set;
  }
}

export async function uploadCostPriceFile(input: UploadCostPriceFileInput): Promise<CostPriceChangeSetDetail> {
  const body = new FormData();
  body.append('file', input.file);
  body.append('supplier_id', input.supplier.id);
  body.append('currency', input.currency);
  if (input.start_date) body.append('start_date', input.start_date);
  if (input.end_date) body.append('end_date', input.end_date);
  const res = await apiFetch(BASE, { method: 'POST', body });
  if (!res.ok) {
    if (res.status === 409) {
      try {
        const parsed = (await res.clone().json()) as { detail?: { open_set?: { id: string; code: string } } };
        if (parsed?.detail?.open_set) throw new OpenSetExistsError(parsed.detail.open_set);
      } catch (error) {
        if (error instanceof OpenSetExistsError) throw error;
        // Not a parseable open_set body - fall through to the generic message below.
      }
    }
    throw new Error(await extractApiError(res, 'Failed to upload the price list'));
  }
  return (await res.json()) as CostPriceChangeSetDetail;
}

// ---------------------------------------------------------------------------
// 1.3 list, 1.4 detail, 1.5 lines
// ---------------------------------------------------------------------------

export interface CostPriceListParams extends DataGridParamsInput {
  status?: string[];
  supplier_id?: string;
}

export async function getCostPriceChangeSets(
  params: CostPriceListParams,
): Promise<{ data: CostPriceChangeSetListItem[]; total: number; page: number; limit: number }> {
  const sp = buildDataGridParams(params, {
    status: params.status?.length ? params.status.join(',') : undefined,
    supplier_id: params.supplier_id,
  });
  const res = await apiFetch(`${BASE}?${sp.toString()}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load cost price uploads'));
  return res.json();
}

export async function getCostPriceChangeSet(id: string): Promise<CostPriceChangeSetDetail> {
  const res = await apiFetch(`${BASE}/${id}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load this cost price upload'));
  return (await res.json()) as CostPriceChangeSetDetail;
}

export async function getCostPriceChangeLines(id: string): Promise<{ data: CostPriceChangeLine[] }> {
  const res = await apiFetch(`${BASE}/${id}/lines`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the lines'));
  return (await res.json()) as { data: CostPriceChangeLine[] };
}

// ---------------------------------------------------------------------------
// 1.6 map / skip / lead time
// ---------------------------------------------------------------------------

export interface PatchLineInput {
  product_id?: string | null;
  skipped?: boolean;
  skip_reason?: string;
  new_link_lead_time_days?: number;
}

export async function patchCostPriceChangeLine(
  setId: string,
  lineId: string,
  patch: PatchLineInput,
): Promise<{ line: CostPriceChangeLine; counts: CostPriceChangeSetCounts; actions: CostPriceChangeSetDetail['actions'] }> {
  const res = await apiFetch(`${BASE}/${setId}/lines/${lineId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to update this line'));
  return res.json();
}

// ---------------------------------------------------------------------------
// 1.7 verification
// ---------------------------------------------------------------------------

export async function submitCostPriceChangeSet(id: string): Promise<CostPriceChangeSetDetail> {
  const res = await apiFetch(`${BASE}/${id}/submit`, { method: 'POST' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to submit for verification'));
  return (await res.json()) as CostPriceChangeSetDetail;
}

export async function decideCostPriceLine(
  setId: string,
  lineId: string,
  decision: LineDecision,
  reason?: string,
): Promise<{ line: CostPriceChangeLine; counts: CostPriceChangeSetCounts; actions: CostPriceChangeSetDetail['actions'] }> {
  const res = await apiFetch(`${BASE}/${setId}/lines/${lineId}/decision`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, reason }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to record this decision'));
  return res.json();
}

export async function decideAllCostPriceLines(id: string, decision: 'accepted' | 'rejected'): Promise<CostPriceChangeSetDetail> {
  const res = await apiFetch(`${BASE}/${id}/decide-all`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to decide the undecided lines'));
  return (await res.json()) as CostPriceChangeSetDetail;
}

export async function returnCostPriceChangeSet(id: string, reason: string): Promise<CostPriceChangeSetDetail> {
  const res = await apiFetch(`${BASE}/${id}/return`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to return this set'));
  return (await res.json()) as CostPriceChangeSetDetail;
}

// ---------------------------------------------------------------------------
// 1.8 apply
// ---------------------------------------------------------------------------

export async function applyCostPriceChangeSet(id: string): Promise<CostPriceChangeSetDetail> {
  const res = await apiFetch(`${BASE}/${id}/apply`, { method: 'POST' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to apply this set'));
  return (await res.json()) as CostPriceChangeSetDetail;
}

// ---------------------------------------------------------------------------
// S6: re-capture current prices on a Draft set whose lines went stale.
// ---------------------------------------------------------------------------

export async function refreshCostPricePrices(id: string): Promise<CostPriceChangeSetDetail> {
  const res = await apiFetch(`${BASE}/${id}/refresh-prices`, { method: 'POST' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to refresh prices'));
  return (await res.json()) as CostPriceChangeSetDetail;
}

// ---------------------------------------------------------------------------
// 1.10 source file, 1.11 history
// ---------------------------------------------------------------------------

export async function downloadCostPriceSourceFile(id: string): Promise<void> {
  const res = await apiFetch(`${BASE}/${id}/source-file`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to download the source file'));
  const blob = await res.blob();
  const disposition = res.headers.get('content-disposition') ?? '';
  const match = disposition.match(/filename="?([^";]+)"?/);
  const filename = match?.[1] ?? 'price-list.xlsx';
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export async function getCostPriceChangeSetHistory(id: string): Promise<{ data: CostPriceHistoryEvent[] }> {
  const res = await apiFetch(`${BASE}/${id}/history`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load history'));
  return (await res.json()) as { data: CostPriceHistoryEvent[] };
}

// ---------------------------------------------------------------------------
// Product picker for "Not found" lines (contract section 6) - the real product
// select, `value` set to the product's own id (never shown, only the code/description
// are rendered) since a manual map writes `product_id`.
// ---------------------------------------------------------------------------

export async function searchCostPriceProductOptions(query: string): Promise<SearchableSelectOption[]> {
  const sp = new URLSearchParams({ limit: '50' });
  if (query.trim()) sp.set('query', query.trim());
  const res = await apiFetch(`/api/v1/master-data/products/select?${sp.toString()}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load products'));
  const body = (await res.json()) as { data: { id: string; product_code: string; product_name: string }[] };
  return body.data.map((p) => ({
    value: p.id,
    label: p.product_code,
    description: p.product_name,
    searchText: `${p.product_code} ${p.product_name}`,
  }));
}

// ---------------------------------------------------------------------------
// Cost lists (contract section 2) - the real `product_supplier_costs` rows,
// through the supplier cost-lists route (Prices tab) and the by-product route's
// own `costs` field (Suppliers tab), both wired at their own call sites.
// ---------------------------------------------------------------------------

export async function getSupplierCostLists(
  supplierId: string,
  params: { query?: string; status?: string[] } = {},
): Promise<{ data: SupplierCostListEntry[]; today: string }> {
  const sp = new URLSearchParams();
  if (params.query) sp.set('query', params.query);
  if (params.status?.length) sp.set('status', params.status.join(','));
  const qs = sp.toString();
  const res = await apiFetch(`/api/v1/procurement/suppliers/${supplierId}/cost-lists${qs ? `?${qs}` : ''}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load this supplier’s prices'));
  return res.json();
}

export interface CostRowInput {
  unit_cost: number;
  currency: string;
  start_date: string | null;
  end_date: string | null;
}

export async function createProductSupplierCost(linkId: string, input: CostRowInput): Promise<ProductSupplierCostRow> {
  const res = await apiFetch(`/api/v1/procurement/product-suppliers/${linkId}/costs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to save the price'));
  return (await res.json()) as ProductSupplierCostRow;
}

export async function updateProductSupplierCost(
  linkId: string,
  costId: string,
  input: CostRowInput,
): Promise<ProductSupplierCostRow> {
  const res = await apiFetch(`/api/v1/procurement/product-suppliers/${linkId}/costs/${costId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to save the price'));
  return (await res.json()) as ProductSupplierCostRow;
}
