/**
 * ============================================================================
 * SCM fulfilment - the supplier stock list and the container loading plan
 * ============================================================================
 * Layering: LoadingPlanView -> THIS service -> lib/api-client -> backend.
 *
 * ── BACKEND CONTRACT (app/api/v1/scm/fulfilment.py) ────────────────────────
 *
 *  POST /api/v1/scm/supplier-inventory/preview   -> 200 StockListPreview
 *  POST /api/v1/scm/supplier-inventory/apply     -> 200 StockListResult
 *       ?validate_only=true                      -> 200 UploadTestResult
 *       multipart: file + supplier_id. Auth: `scm.reorder.run`.
 *  GET  /api/v1/scm/supplier-inventory?supplier_id=   -> 200 SupplierStock
 *  GET  /api/v1/scm/supplier-inventory/unfinished     -> 200 { rows }
 *  GET  /api/v1/scm/container-sizes                   -> 200 { sizes }
 *  POST /api/v1/scm/loading-plans                     -> 201 LoadingPlan
 *  PATCH/GET/DELETE /api/v1/scm/loading-plans/{id}
 *
 * The supplier travels WITH the file because the sheet never says who wrote it:
 * it carries model numbers and quantities and nothing else. That is the only
 * question this upload asks.
 *
 * Apply REPLACES the supplier's snapshot, so preview-then-confirm is not
 * ceremony here - a wrong file applied in one click deletes what we hold.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { UploadTestResult } from '../reorder/components/UploadTestVerdict';

export interface StockListSummary {
  rows: number;
  items_matched: number;
  items_unmatched: number;
  unmatched_item_codes: string[];
  qty_packed: number;
  qty_unfinished: number;
  /** Packed x measured volume. What a container could actually be filled from. */
  loadable_cbm: number;
  items_unmeasured: number;
  unmeasured_item_codes: string[];
  unmapped_headers: string[];
  unreadable_rows: number;
}

export interface StockListPreview {
  /** Named `ok` to satisfy the shared two-step upload hook. */
  ok: boolean;
  readable: boolean;
  missing_columns: string[];
  problems: { row: number; reason: string }[];
  supplier_id: string;
  supplier_name: string | null;
  /** How many rows this upload would replace. Zero on a first upload. */
  rows_held_now: number;
  sample: {
    item_code: string;
    product_name: string | null;
    qty_packed: number;
    qty_unfinished: number;
    cbm_per_unit: number | null;
  }[];
  summary: StockListSummary | Record<string, never>;
}

export interface StockListResult {
  readable: boolean;
  missing_columns: string[];
  supplier_id: string;
  supplier_name: string | null;
  as_of: string;
  rows_written: number;
  rows_replaced: number;
  duplicate_models_merged: number;
  summary: StockListSummary;
}

export interface SupplierStockRow {
  item_code: string;
  product_id: string | null;
  product_name: string | null;
  qty_packed: number;
  qty_unfinished: number;
  cbm_per_unit: number | null;
  matched: boolean;
}

export interface SupplierStock {
  supplier_id: string;
  as_of: string | null;
  rows: SupplierStockRow[];
}

export interface UnfinishedRow {
  item_code: string;
  product_name: string | null;
  qty_unfinished: number;
  qty_packed: number;
  as_of: string | null;
}

export interface ContainerSize {
  id: string;
  code: string;
  label: string | null;
  cbm: number;
  is_default: boolean;
}

export type LoadingLineStatus = 'allocated' | 'partial' | 'deferred' | 'unmeasured';

export type DeferralReason =
  | 'over_capacity'
  | 'no_packed_stock'
  | 'not_in_stock_list'
  | 'no_volume_on_file';

export interface RankFactor {
  key: string;
  weight: number;
  value: number | null;
  present: boolean;
}

export interface LoadingPlanLine {
  id: string;
  po_line_id: string;
  po_number: string | null;
  item_code: string | null;
  qty_outstanding: number;
  qty_packed_available: number | null;
  qty_planned: number;
  cbm_per_unit: number | null;
  cbm_planned: number | null;
  /** Whether the volume came from the supplier's file or our own catalogue dimensions. */
  volume_basis: 'supplier' | 'catalogue' | null;
  rank: number | null;
  rank_score: number | null;
  factors: RankFactor[];
  status: LoadingLineStatus;
  deferral_reason: DeferralReason | null;
}

export interface LoadingPlan {
  id: string;
  supplier_id: string;
  supplier_name: string | null;
  container_type: string | null;
  container_count: number;
  container_cbm: number;
  capacity_cbm: number;
  planned_cbm: number;
  fill_rate: number | null;
  line_count: number;
  deferred_count: number;
  unmeasured_count: number;
  inventory_as_of: string | null;
  computed_at: string | null;
  created_by: string | null;
  lines?: LoadingPlanLine[];
}

async function readJson<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) throw new Error(await extractApiError(res, fallback));
  return (await res.json()) as T;
}

function stockForm(file: File, supplierId: string): FormData {
  const body = new FormData();
  body.append('file', file);
  body.append('supplier_id', supplierId);
  return body;
}

export async function previewStockList(
  file: File,
  supplierId: string,
): Promise<StockListPreview> {
  const res = await apiFetch('/api/v1/scm/supplier-inventory/preview', {
    method: 'POST',
    body: stockForm(file, supplierId),
  });
  const body = await readJson<Omit<StockListPreview, 'ok'>>(res, 'Failed to read the stock list');
  // The backend calls it `readable`; the shared upload hook asks for `ok`.
  return { ...body, ok: body.readable };
}

export async function applyStockList(file: File, supplierId: string): Promise<StockListResult> {
  const res = await apiFetch('/api/v1/scm/supplier-inventory/apply', {
    method: 'POST',
    body: stockForm(file, supplierId),
  });
  return readJson<StockListResult>(res, 'Failed to save the stock list');
}

export async function testStockList(file: File, supplierId: string): Promise<UploadTestResult> {
  const res = await apiFetch('/api/v1/scm/supplier-inventory/apply?validate_only=true', {
    method: 'POST',
    body: stockForm(file, supplierId),
  });
  return readJson<UploadTestResult>(res, 'Failed to test the stock list');
}

export async function getSupplierStock(supplierId: string): Promise<SupplierStock> {
  const res = await apiFetch(
    `/api/v1/scm/supplier-inventory?supplier_id=${encodeURIComponent(supplierId)}`,
  );
  return readJson<SupplierStock>(res, 'Failed to load the supplier stock list');
}

export async function getUnfinishedStock(supplierId: string): Promise<UnfinishedRow[]> {
  const res = await apiFetch(
    `/api/v1/scm/supplier-inventory/unfinished?supplier_id=${encodeURIComponent(supplierId)}`,
  );
  const body = await readJson<{ rows: UnfinishedRow[] }>(res, 'Failed to load unfinished stock');
  return body.rows;
}

export async function getContainerSizes(): Promise<ContainerSize[]> {
  const res = await apiFetch('/api/v1/scm/container-sizes');
  const body = await readJson<{ sizes: ContainerSize[] }>(res, 'Failed to load container sizes');
  return body.sizes;
}

export interface ContainerSizeWrite {
  code: string;
  label: string | null;
  cbm: number;
  is_default: boolean;
  is_active: boolean;
}

export async function createContainerSize(body: ContainerSizeWrite): Promise<ContainerSize[]> {
  const res = await apiFetch('/api/v1/scm/container-sizes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const out = await readJson<{ sizes: ContainerSize[] }>(res, 'Failed to add the container size');
  return out.sizes;
}

export async function updateContainerSize(
  id: string,
  body: ContainerSizeWrite,
): Promise<ContainerSize[]> {
  const res = await apiFetch(`/api/v1/scm/container-sizes/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const out = await readJson<{ sizes: ContainerSize[] }>(res, 'Failed to save the container size');
  return out.sizes;
}

export async function deleteContainerSize(id: string): Promise<void> {
  const res = await apiFetch(`/api/v1/scm/container-sizes/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to delete the container size'));
}

export interface LoadingPlanRequest {
  supplier_id: string;
  container_count: number;
  container_type?: string | null;
  container_cbm?: number | null;
}

export async function createLoadingPlan(body: LoadingPlanRequest): Promise<LoadingPlan> {
  const res = await apiFetch('/api/v1/scm/loading-plans', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return readJson<LoadingPlan>(res, 'Failed to build the loading plan');
}

export async function updateLoadingPlan(
  id: string,
  body: { container_count?: number; container_type?: string | null },
): Promise<LoadingPlan> {
  const res = await apiFetch(`/api/v1/scm/loading-plans/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return readJson<LoadingPlan>(res, 'Failed to re-run the loading plan');
}

export async function getLoadingPlans(supplierId?: string): Promise<LoadingPlan[]> {
  const qs = supplierId ? `?supplier_id=${encodeURIComponent(supplierId)}` : '';
  const res = await apiFetch(`/api/v1/scm/loading-plans${qs}`);
  const body = await readJson<{ data: LoadingPlan[] }>(res, 'Failed to load loading plans');
  return body.data;
}

export async function getLoadingPlan(id: string): Promise<LoadingPlan> {
  const res = await apiFetch(`/api/v1/scm/loading-plans/${id}`);
  return readJson<LoadingPlan>(res, 'Failed to load the loading plan');
}

export async function deleteLoadingPlan(id: string): Promise<void> {
  const res = await apiFetch(`/api/v1/scm/loading-plans/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to delete the loading plan'));
}

/** Suppliers, from the existing procurement select. Value is the id the API needs. */
export async function getFulfilmentSuppliers(): Promise<{ value: string; label: string }[]> {
  const res = await apiFetch('/api/v1/procurement/suppliers/select');
  const rows = await readJson<{ id: string; supplier_name: string }[]>(
    res,
    'Failed to load suppliers',
  );
  return rows.map((s) => ({ value: s.id, label: s.supplier_name }));
}
