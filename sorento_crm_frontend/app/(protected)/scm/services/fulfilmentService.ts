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
import {
  filenameFromContentDisposition,
  saveBlobAs,
} from '@/app/(protected)/project-sales/_shared/services/fileDownload';
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

/**
 * Suppliers, from the existing procurement select. Value is the id the API needs.
 *
 * The endpoint caps at 100 rows (`app/api/v1/procurement/suppliers.py`), so a bare no-query
 * call is only ever a first page - fine for a short client-filtered pool, silently wrong for
 * a book of hundreds of suppliers where the one somebody wants is past row 100 and simply
 * never reachable by typing its name. `query` ilikes code + name server-side and is the fix:
 * pass it (typically from `SearchableSelect`'s own `fetchOptions`, which already debounces
 * and re-queries as the user types) rather than fetching the unfiltered page once and
 * filtering it client-side.
 */
export async function getFulfilmentSuppliers(
  query?: string,
): Promise<{ value: string; label: string }[]> {
  const qs = query?.trim() ? `?query=${encodeURIComponent(query.trim())}` : '';
  const res = await apiFetch(`/api/v1/procurement/suppliers/select${qs}`);
  const rows = await readJson<{ id: string; supplier_name: string }[]>(
    res,
    'Failed to load suppliers',
  );
  return rows.map((s) => ({ value: s.id, label: s.supplier_name }));
}

/**
 * S8 - what a supplier was told, on which channel, and when.
 *
 * `skipped` is an outcome, not a failure. A supplier with no address on file, and the chat
 * channel that has nothing to send to yet, both land there with a reason, and the document is
 * still produced so it can be sent by hand.
 */
export interface SupplierNotice {
  id: string;
  supplier_id: string;
  supplier_name: string | null;
  loading_plan_id: string | null;
  notice_type: string;
  channel: 'email' | 'chat';
  recipient: string | null;
  status: 'pending' | 'sent' | 'failed' | 'skipped';
  status_reason: string | null;
  sent_at: string | null;
  attempt_count: number;
  last_error: string | null;
  document_filename: string | null;
  has_document: boolean;
  container_type: string | null;
  container_count: number | null;
  planned_cbm: number | null;
  line_count: number;
  production_line_count: number;
  created_at: string | null;
  created_by: string | null;
}

export async function approveLoadingPlan(
  planId: string,
): Promise<{ notices: SupplierNotice[]; document_filename: string }> {
  const res = await apiFetch(`/api/v1/scm/loading-plans/${planId}/notices`, { method: 'POST' });
  return readJson(res, 'Failed to send the supplier notice');
}

export async function getPlanNotices(planId: string): Promise<SupplierNotice[]> {
  const res = await apiFetch(`/api/v1/scm/loading-plans/${planId}/notices`);
  const body = await readJson<{ data: SupplierNotice[] }>(res, 'Failed to load the notices');
  return body.data;
}

export async function getNoticeDocumentUrl(
  noticeId: string,
): Promise<{ url: string; filename: string | null }> {
  const res = await apiFetch(`/api/v1/scm/supplier-notices/${noticeId}/document`);
  return readJson(res, 'Failed to open the notice document');
}

/**
 * Stage 1 - the container request (demand-first, PLAN-scm-loading-plan-demand-first.md,
 * amended section 4 - 20 Aug afternoon).
 *
 * `build` is a pure read: ONE table over every product on the supplier's current stock list.
 * Rows with open sales-order need (`has_demand: true`) are ranked against the ACTIVE
 * Fulfilment Priority policy and carry a NETTED `suggested_qty`
 * (`max(open_so_need - on_hand - incoming_spo - outstanding_po, 0)`) - the gross
 * `open_so_need` and the three stock figures stay on the row so the arithmetic is visible.
 * Rows on the stock list with no open need (`has_demand: false`) sort after them, suggested 0,
 * unranked - nothing the stock list holds vanishes in the merge. `include_lines=true` (always
 * requested by this FE - the matrix and the SO drill both need it) adds the flat open-SO lines
 * behind every demand row. `send` turns Ms Tee's reviewed lines into a notice through the same
 * S8 machinery `approveLoadingPlan` uses.
 *
 * ── BACKEND CONTRACT (app/api/v1/scm/container_requests.py) ────────────────
 *  POST /api/v1/scm/container-requests/build?include_lines=true -> 200 ContainerRequestBuild.
 *       Auth: `scm.dashboard.view`.
 *  POST /api/v1/scm/container-requests       -> 201 { notices, document_filename }. Auth: `scm.reorder.run`.
 */
export interface ContainerRequestRow {
  product_id: string;
  item_code: string | null;
  product_name: string | null;
  /** Gross outstanding SO need, all classes - what the Need column shows. */
  open_so_need: number;
  /** NETTED against on_hand / incoming_spo / outstanding_po, floored at 0 - the editable ask. */
  suggested_qty: number;
  on_hand: number;
  incoming_spo: number;
  outstanding_po: number;
  /** Gross split - explains the NEED, not the netted `suggested_qty`. */
  project_qty: number;
  retail_qty: number;
  unclassified_qty: number;
  earliest_required_date: string | null;
  so_count: number;
  qty_packed: number;
  qty_unfinished: number;
  cbm_per_unit: number | null;
  row_as_of: string | null;
  /** Null on a `has_demand: false` row - nothing to rank it by. */
  rank: number | null;
  rank_score: number | null;
  rank_factors: RankFactor[];
  /** False for a stock-list product with no open sales-order need behind it - still shown
   *  (one table), just unranked and muted. */
  has_demand: boolean;
}

/** One open SO line behind a demand row - `include_lines=true` on the build. Flat, so the FE
 *  can bucket them into a schedule matrix or answer "which order does this cover" without a
 *  second fetch. `sum(qty per product) === that row's open_so_need`. */
export interface ContainerRequestSoLine {
  product_id: string;
  item_code: string | null;
  so_number: string | null;
  customer_label: string | null;
  demand_class: string | null;
  order_date: string | null;
  required_date: string | null;
  qty: number;
}

/** The latest ingest per document family - "as of when" for every figure the build shows. */
export interface ContainerRequestSources {
  so_book_as_of: string | null;
  po_book_as_of: string | null;
  spo_as_of: string | null;
  stock_list_as_of: string | null;
}

export interface ContainerRequestBuild {
  supplier_id: string;
  /** Null when this supplier has no stock list applied yet - the FE's cue for the "upload a
   *  stock list first" empty state. */
  stock_list_as_of: string | null;
  rows: ContainerRequestRow[];
  sources: ContainerRequestSources;
  /** Present when the build was called with `include_lines=true` (always, from this FE). */
  lines?: ContainerRequestSoLine[];
}

export async function buildContainerRequest(supplierId: string): Promise<ContainerRequestBuild> {
  const res = await apiFetch('/api/v1/scm/container-requests/build?include_lines=true', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ supplier_id: supplierId }),
  });
  return readJson<ContainerRequestBuild>(res, 'Failed to work out what to ask this supplier for');
}

export interface ContainerRequestLine {
  product_id: string;
  qty: number;
}

export async function sendContainerRequest(
  supplierId: string,
  lines: ContainerRequestLine[],
): Promise<{ notices: SupplierNotice[]; document_filename: string }> {
  const res = await apiFetch('/api/v1/scm/container-requests', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ supplier_id: supplierId, lines }),
  });
  return readJson(res, 'Failed to send the request to the supplier');
}

/** Every notice this supplier has ever been sent, across both stages - filtered client-side
 *  to `notice_type` where a caller needs only one stage's history. */
export async function getSupplierNotices(supplierId: string): Promise<SupplierNotice[]> {
  const res = await apiFetch(
    `/api/v1/scm/supplier-notices?supplier_id=${encodeURIComponent(supplierId)}`,
  );
  const body = await readJson<{ data: SupplierNotice[] }>(res, 'Failed to load the notices');
  return body.data;
}

/**
 * S9 - the packing list, and what each container draws down.
 *
 * `quantity_to_allocate` is what is LEFT on a line, never the shipped figure again: re-opening
 * the screen after a partial allocation must not propose the same units twice.
 */
export interface AllocationOption {
  po_line_id: string;
  po_number: string | null;
  warehouse_id: string | null;
  warehouse_code: string | null;
  outstanding: number;
  expected_date: string | null;
  score: number;
  factors: { key: string; weight: number; value: number | null; present: boolean }[];
  qty?: number;
}

export interface AllocationLine {
  shipment_line_id: string;
  product_id: string;
  quantity_shipped: number;
  quantity_allocated: number;
  quantity_to_allocate: number;
  reason: 'only_open_order' | 'highest_priority' | 'no_open_order';
  suggestion: AllocationOption | null;
  alternatives: AllocationOption[];
}

export interface AllocationSuggestion {
  shipment_id: string;
  shipment_number: string | null;
  container_no: string | null;
  supplier_id: string | null;
  lines: AllocationLine[];
}

export interface PackingListBlock {
  index: number;
  shipment_number: string;
  container_no: string | null;
  bl_no: string | null;
  lines: number;
  qty: number;
  cartons: number | null;
  unmatched_items: string[];
}

export interface PackingListPreview {
  ok: boolean;
  blocks: PackingListBlock[];
  block_count: number;
  line_count: number;
  rows_read: number;
  unmatched_item_codes: string[];
  unmatched_items: number;
  unmapped_headers: string[];
  missing_columns: string[];
  problems: string[];
  /** Null when neither the file, the form nor the supplier's price list says. */
  currency?: string | null;
  /** Which of those said it: `form` | `document` | `supplier_price_list` | `none`. */
  currency_source?: string | null;
  priced_lines?: number;
}

/** What the supplier and currency form fields are called on both packing-list endpoints. */
interface PackingListUploadOptions {
  supplierId?: string | null;
  currency?: string | null;
}

function packingListForm(file: File, opts: PackingListUploadOptions): FormData {
  const body = new FormData();
  body.append('file', file);
  if (opts.supplierId) body.append('supplier_id', opts.supplierId);
  // Only when the operator typed one: an empty string would be read as a currency the
  // backend cannot resolve and refuse the upload the document itself could have answered.
  if (opts.currency) body.append('currency', opts.currency);
  return body;
}

export async function previewPackingList(
  file: File,
  opts: PackingListUploadOptions = {},
): Promise<PackingListPreview> {
  const res = await apiFetch('/api/v1/scm/packing-lists/preview', {
    method: 'POST',
    body: packingListForm(file, opts),
  });
  return readJson<PackingListPreview>(res, 'Failed to read the packing list');
}

export async function applyPackingList(
  file: File,
  opts: PackingListUploadOptions & { shipmentDate?: string | null; validateOnly?: boolean } = {},
): Promise<Record<string, unknown>> {
  const body = packingListForm(file, opts);
  if (opts.shipmentDate) body.append('shipment_date', opts.shipmentDate);
  const qs = opts.validateOnly ? '?validate_only=true' : '';
  const res = await apiFetch(`/api/v1/scm/packing-lists/apply${qs}`, { method: 'POST', body });
  return readJson(res, 'Failed to import the packing list');
}

export async function getAllocationSuggestion(shipmentId: string): Promise<AllocationSuggestion> {
  const res = await apiFetch(`/api/v1/scm/inbound-shipments/${shipmentId}/allocation-suggestion`);
  return readJson<AllocationSuggestion>(res, 'Failed to work out what this container draws down');
}

export interface AllocationDecision {
  shipment_line_id: string;
  splits: { po_line_id: string | null; warehouse_id: string; qty: number }[];
}

export async function approveAllocations(
  shipmentId: string,
  decisions: AllocationDecision[],
): Promise<{ allocations_written: number; purchase_order_lines_advanced: number }> {
  const res = await apiFetch(`/api/v1/scm/inbound-shipments/${shipmentId}/allocations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decisions }),
  });
  return readJson(res, 'Failed to approve the allocations');
}

export interface IncomingShipment {
  shipment_id: string;
  shipment_number: string | null;
  container_no: string | null;
  bl_no: string | null;
  status: string | null;
  lines: number;
  created_at: string | null;
  /** Every factory that loaded this container, not just the one the header names: one
   *  container is routinely filled by two or three suppliers, and the header goes null
   *  once it is mixed. */
  suppliers?: { supplier_id: string; supplier_code: string | null; supplier_name: string | null }[];
}

export async function getIncomingShipments(supplierId?: string | null): Promise<IncomingShipment[]> {
  const qs = supplierId ? `?supplier_id=${encodeURIComponent(supplierId)}` : '';
  const res = await apiFetch(`/api/v1/scm/inbound-shipments${qs}`);
  const body = await readJson<{ data: IncomingShipment[] }>(res, 'Failed to load the containers');
  return body.data;
}

/**
 * S10 - the Sorento packing list: one container, every factory that loaded it.
 *
 * ── BACKEND CONTRACT ───────────────────────────────────────────────────────
 *  GET /api/v1/scm/inbound-shipments/{id}/packing-list        -> 200 ConsolidatedPackingList
 *  GET /api/v1/scm/inbound-shipments/{id}/packing-list/export -> 200 .xlsx bytes
 *       Content-Disposition: attachment; filename="<container>-packing-list.xlsx"
 *  Auth on both: `scm.dashboard.view`. 200 with no factories on an empty container;
 *  404 only when the shipment id is unknown.
 *
 * `discrepancies` and `company` are DERIVED - the first from the loading plan the supplier
 * was sent, the second from the product's brand. Neither is ever typed in, which is why they
 * arrive as strings to print rather than as fields to edit.
 */
export type PackingListCompany = 'SORENTO' | 'MOCHA';

export interface PackingListLine {
  line_id: string;
  product_id: string;
  product_code: string;
  product_name: string | null;
  brand: string | null;
  company: PackingListCompany;
  qty: number;
  cartons: number | null;
  /** Null when neither the supplier's file nor our catalogue dimensions give a volume. */
  cbm: number | null;
  /** What the supplier wrote on the line, never our own words. */
  remarks: string | null;
  /** Where this differs from the loading plan we sent that supplier. */
  discrepancies: string[];
}

/** On the loading plan, absent from what the supplier actually loaded. */
export interface PackingListNotPacked {
  product_id: string;
  product_code: string;
  product_name: string | null;
  planned_qty: number;
}

export interface PackingListTotals {
  lines: number;
  qty: number;
  cartons: number;
  cbm: number;
  /** How many of `lines` the cbm sum actually knows a volume for. A partial figure read as
   *  a full one is how a container gets planned against a volume nobody measured. */
  cbm_known_lines?: number;
}

export interface PackingListSplitRow extends PackingListTotals {
  company: PackingListCompany;
}

export interface PackingListFactory {
  supplier_id: string | null;
  supplier_code: string | null;
  supplier_name: string | null;
  loading_plan_id: string | null;
  /** Null when the supplier was never sent a loading plan, so nothing can be compared. */
  notice_id: string | null;
  /**
   * Whether that plan actually asked for a packing quantity.
   *
   * A notice whose lines are all `produce` is a production instruction, not a loading plan:
   * it exists, but there is nothing in it to compare a shipment against. Without this the
   * screen would claim a comparison it never made.
   */
  has_pack_plan: boolean;
  /** When that plan was raised, and when it actually reached the supplier. A shipment is
   *  compared against a plan of a particular date, and an old plan is worth seeing. */
  notice_created_at: string | null;
  notice_sent_at: string | null;
  lines: PackingListLine[];
  not_packed: PackingListNotPacked[];
  subtotal: PackingListTotals;
}

export interface ConsolidatedPackingList {
  shipment_id: string;
  shipment_number: string | null;
  container_no: string | null;
  bl_no: string | null;
  status: string | null;
  factories: PackingListFactory[];
  total: PackingListTotals;
  /** Both companies, always, zeros included: an absent row reads as a missing figure. */
  split: PackingListSplitRow[];
}

export async function getConsolidatedPackingList(
  shipmentId: string,
): Promise<ConsolidatedPackingList> {
  const res = await apiFetch(`/api/v1/scm/inbound-shipments/${shipmentId}/packing-list`);
  return readJson<ConsolidatedPackingList>(res, 'Failed to load the packing list');
}

/**
 * The same list as the file Ms Tee used to build by hand.
 *
 * The name comes from the server's `Content-Disposition` rather than being rebuilt here, so
 * the download and the sheet inside it agree on which container this is. `fallbackName` is
 * what the file is called if the header is missing - the container or shipment number, never
 * the shipment id, because a downloaded file named after a UUID tells its reader nothing.
 */
export async function downloadPackingListExport(
  shipmentId: string,
  fallbackName?: string | null,
): Promise<void> {
  const res = await apiFetch(`/api/v1/scm/inbound-shipments/${shipmentId}/packing-list/export`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to export the packing list'));
  const filename =
    filenameFromContentDisposition(res.headers.get('Content-Disposition')) ??
    `${fallbackName || 'container'}-packing-list.xlsx`;
  saveBlobAs(await res.blob(), filename);
}
