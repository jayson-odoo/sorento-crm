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
 *  GET  /api/v1/scm/supplier-inventory/stock-list-file?supplier_id= -> 200 SupplierStockListFile
 *       The uploaded sheet itself, retained as a resource attachment on apply (best-effort;
 *       `attachment_id` is null when nothing was uploaded, or the retain failed). Preview it
 *       through the SAME `/api/v1/resource-management/attachments/{id}/...` routes and shared
 *       `AttachmentPreviewModal` Resource Management uses - no bespoke viewer for one xlsx.
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
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
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

/** The retained copy of the supplier's own sheet, if the last apply kept one. */
export interface SupplierStockListFile {
  supplier_id: string;
  attachment_id: string | null;
  filename: string | null;
  uploaded_at: string | null;
}

export async function getSupplierStockListFile(supplierId: string): Promise<SupplierStockListFile> {
  const res = await apiFetch(
    `/api/v1/scm/supplier-inventory/stock-list-file?supplier_id=${encodeURIComponent(supplierId)}`,
  );
  return readJson<SupplierStockListFile>(res, 'Failed to load the stored stock list');
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

/* ─────────────────────────────────────────────────────────────────────────────
 * The plan as a RECORD (part 4, R1-R6)
 *
 * A container plan used to be React state on one page: leave it and it was gone, two people
 * could not look at the same one, and there was nothing to cancel, delete or reopen. It is
 * now a row in `scm.loading_plan` - the table the supplier notices already point at - listed
 * at `/scm/loading-plan` and opened at `/scm/loading-plan/{id}`.
 *
 * ── BACKEND CONTRACT (app/api/v1/scm/fulfilment.py) ────────────────────────
 *  GET    /api/v1/scm/loading-plans?page&limit&sort&dir&query&status -> 200 {data,total}
 *  POST   /api/v1/scm/loading-plans        -> 201 LoadingPlanRecord. Auth: `scm.reorder.run`.
 *  POST   /api/v1/scm/loading-plans/{id}/cancel -> 200 LoadingPlanRecord
 *  PUT    /api/v1/scm/loading-plans/{id}/edits  -> 200 LoadingPlanRecord
 *  DELETE /api/v1/scm/loading-plans/{id}   -> 204, or 409 `plan_sent` once a notice exists.
 * ────────────────────────────────────────────────────────────────────────── */

export type LoadingPlanStatus = 'planning' | 'sent' | 'cancelled';

/** Which document the plan was started from. `none` is a real answer, not a missing one. */
export type PlanDocumentKind = 'stock_list' | 'proforma' | 'none';

export interface LoadingPlanRecord {
  id: string;
  supplier_id: string;
  supplier_name: string | null;
  /** When somebody started planning this container. The row has no number: it is named by
   *  supplier and start time, exactly as a reorder run is. */
  started_at: string;
  /** "Sales order cut-off". Null = every open order counts. */
  plan_horizon_date: string | null;
  document_kind: PlanDocumentKind;
  /** Ready to print: "Stock list 27/07/2026" / "Proforma invoice PI-x" / "No file". */
  document_label: string;
  source_attachment_id: string | null;
  status: LoadingPlanStatus;
  /** The latest notice for this plan, so the list can say how and when it went out. */
  sent_channel: 'email' | 'chat' | null;
  sent_at: string | null;
  /** When the supplier first opened the link. Always null until S3 lands the tracking. */
  opened_at: string | null;
  cancelled_at: string | null;
  cancelled_by: string | null;
  /** The typed quantities, `row_key -> qty`. Applied to `suggested_qty` by the build. */
  line_edits: Record<string, number>;
  /** What the last build of this plan asked for, so the list does not have to re-run one
   *  build per row to fill a column. Null before the plan has ever been opened. */
  to_request_qty: number | null;
  to_request_cbm: number | null;
}

export interface LoadingPlanListParams {
  pageIndex: number;
  pageSize: number;
  sorting: { id: string; desc: boolean }[];
  searchQuery: string;
  /** `active` = planning + sent, the default chip. */
  status: LoadingPlanStatus | 'active' | '';
}

export async function getLoadingPlanList(
  params: LoadingPlanListParams,
): Promise<{ data: LoadingPlanRecord[]; total: number }> {
  const qs = buildDataGridParams(params, { status: params.status });
  const res = await apiFetch(`/api/v1/scm/loading-plans?${qs.toString()}`);
  return readJson(res, 'Failed to load the loading plans');
}

export interface LoadingPlanCreate {
  supplier_id: string;
  plan_horizon_date: string | null;
  document_kind: PlanDocumentKind;
  source_attachment_id: string | null;
}

export async function createLoadingPlanRecord(
  body: LoadingPlanCreate,
): Promise<LoadingPlanRecord> {
  const res = await apiFetch('/api/v1/scm/loading-plans', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return readJson<LoadingPlanRecord>(res, 'Failed to start the plan');
}

/**
 * Change the sales order cut-off on an open plan (the gear's "Change cut-off", R5).
 *
 * A PATCH on the plan, not a new plan: the buyer is narrowing the same ask, and starting a
 * second row for it would leave two plans for one container with nothing to tell them apart.
 */
export async function updateLoadingPlanCutOff(
  id: string,
  planHorizonDate: string | null,
): Promise<LoadingPlanRecord> {
  const res = await apiFetch(`/api/v1/scm/loading-plans/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ plan_horizon_date: planHorizonDate }),
  });
  return readJson<LoadingPlanRecord>(res, 'Failed to change the cut-off');
}

export async function cancelLoadingPlan(id: string): Promise<LoadingPlanRecord> {
  const res = await apiFetch(`/api/v1/scm/loading-plans/${id}/cancel`, { method: 'POST' });
  return readJson<LoadingPlanRecord>(res, 'Failed to cancel the plan');
}

/**
 * The typed quantities, WHOLE map, one transaction (R6). Not a patch: what is not in the map
 * is not an edit any more, so a cleared cell cannot survive as a stale override.
 */
export async function saveLoadingPlanEdits(
  id: string,
  edits: Record<string, number>,
): Promise<LoadingPlanRecord> {
  const res = await apiFetch(`/api/v1/scm/loading-plans/${id}/edits`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ line_edits: edits }),
  });
  return readJson<LoadingPlanRecord>(res, 'Failed to save the quantities');
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
  /** The supplier's own stock list with the quantity to load filled in (F4). Container
   *  requests only - a loading notice carries no spreadsheet. */
  xlsx_filename: string | null;
  has_xlsx: boolean;
  /** The read-only page the supplier opens (F8). Built server-side because it has to match
   *  what went out in the email; null once it has expired, been retired by a resend, or when
   *  no public base URL is configured. Both channel rows of one send carry it (R23) - one
   *  credential, delivered two ways. */
  public_url: string | null;
  /** This send HAD a link and it has run out - which is not the same as never having had
   *  one, and is why an older row reads "Link retired" rather than nothing at all. */
  link_retired: boolean;
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
  kind: 'pdf' | 'xlsx' = 'pdf',
): Promise<{ url: string; filename: string | null }> {
  const res = await apiFetch(
    `/api/v1/scm/supplier-notices/${noticeId}/document?kind=${kind}`,
  );
  return readJson(res, 'Failed to open the notice document');
}

/**
 * Stage 1 - the container request (demand-first, PLAN-scm-loading-plan-demand-first.md,
 * amended section 4 - 20 Aug afternoon).
 *
 * `build` is a pure read: ONE table over every product on the supplier's current stock list.
 * Rows with open sales-order need (`has_demand: true`) are ranked against the ACTIVE
 * Fulfilment Priority policy and carry a NETTED `suggested_qty`
 * (`max(open_so_need - on_hand - incoming_spo, 0)`) - `outstanding_po` is NOT subtracted
 * (captain, 20 Aug follow-up: a PO placed but not yet allocated is not supply this container
 * can count on, often the very demand this request is asking the supplier to pack; an SPO
 * allocation is real incoming stock on the water). `outstanding_po` still travels on the row
 * as context and the PO column stays - only the subtraction is gone. The gross `open_so_need`
 * and the three stock figures all stay on the row so the arithmetic is visible.
 * Rows on the stock list with no open need (`has_demand: false`) sort after them, suggested 0,
 * unranked - nothing the stock list holds vanishes in the merge. `include_lines=true` (always
 * requested by this FE - the matrix and the SO drill both need it) adds the flat open-SO lines
 * behind every demand row. `send` turns Ms Tee's reviewed lines into a notice through the same
 * S8 machinery `approveLoadingPlan` uses.
 *
 * `planHorizonDate` ("Plan until", captain 20 Aug) is an optional request field, not a stored
 * column - `build` recomputes on every call, so there is no run row to carry it on. When set,
 * every demand-derived figure (`open_so_need`, `suggested_qty`, the class split, `rank`, and
 * `lines`) counts only demand required on or before it; undated demand is always counted,
 * mirroring the reorder run's own `plan_horizon_date` rule exactly. Omitted/undefined means no
 * cutoff, today's behaviour. The backend echoes back what it actually applied as
 * `plan_horizon_date` on the response.
 *
 * ── BACKEND CONTRACT (app/api/v1/scm/container_requests.py) ────────────────
 *  POST /api/v1/scm/container-requests/build?include_lines=true -> 200 ContainerRequestBuild.
 *       Body: { supplier_id, plan_horizon_date?: "YYYY-MM-DD" }. Auth: `scm.dashboard.view`.
 *  POST /api/v1/scm/container-requests       -> 201 { notices, document_filename }. Auth: `scm.reorder.run`.
 */
export interface ContainerRequestRow {
  /** Whose FIGURES this row shows. On a set row that is the driver member's id (R19), which
   *  is what the SO drill and the twelve-month history are keyed on. */
  product_id: string;
  /** What the GRID keys its rows on: the product id, or the set's own key. Two sets may
   *  share a driver, and a grid keyed on the product id would silently drop one of them. */
  row_key: string;
  /** `set` when the supplier's statement named one of our product sets (R19). Every figure
   *  below is then the DRIVER member's - the member in the fewest sets. */
  row_kind: 'product' | 'set';
  product_set_id: string | null;
  set_code: string | null;
  set_name: string | null;
  /** The member the figures come from, named so the cell can say whose they are. Null on an
   *  ordinary product row. */
  driver_product_id: string | null;
  driver_item_code: string | null;
  driver_product_name: string | null;
  /** The set code on a set row, the product code on a product row - what the supplier is
   *  asked for either way. */
  item_code: string | null;
  product_name: string | null;
  /** Gross outstanding SO need, all classes - what the Need column shows. */
  open_so_need: number;
  /** NETTED against on_hand / incoming_spo only, floored at 0 - the editable ask.
   *  `outstanding_po` is shown below but deliberately not part of this subtraction (captain,
   *  20 Aug follow-up - see the module docstring). The plan's saved edit for this row, when
   *  it has one, is ALREADY applied here (R2). */
  suggested_qty: number;
  /** What the engine worked out before any typed quantity was applied. `Save (N)` counts the
   *  rows where the two differ, and the formula tooltip still explains this figure. */
  engine_qty: number;
  /** SITE POOLS ONLY (`warehouses.segment <> 'project'`), the reorder engine's own predicate.
   *  Stock sitting in a group location is real, but it is spoken for, so it can neither be
   *  asked against nor netted off the ask; it travels beside this as `on_hand_group` and is
   *  shown muted in the row popover. */
  on_hand: number;
  on_hand_group: number;
  /** Open SPO allocations landing at a site pool. Same split, same reason. */
  incoming_spo: number;
  incoming_spo_group: number;
  /** Unreceived packing-list quantity on shipments that have not arrived, any destination.
   *  A REFERENCE beside the ask, never subtracted from it (Q1): a packing list is not
   *  location-specific, so it cannot be netted against a pool the way an SPO can. */
  incoming_pl: number;
  incoming_pl_shipments: ContainerRequestIncomingShipment[];
  /** Placed with a supplier but not yet allocated to a shipment - real context, never
   *  deducted from `suggested_qty`. Company-wide, not pool-only: a PO carries no landing
   *  location until it is allocated. */
  outstanding_po: number;
  outstanding_po_lines: ContainerRequestPoLine[];
  /** On hand and SPO per site pool, zero rows included - a site with nothing in it is a fact
   *  the reader needs, not an absence. */
  sites: ContainerRequestSite[];
  /** Everything the pool predicate excluded, as one muted line. */
  group_locations: ContainerRequestGroupLocations;
  /** Gross split - explains the NEED, not the netted `suggested_qty`. `project_qty` is the
   *  open project SO book net of what CS placed on a PO or an SPO (R15). */
  project_qty: number;
  retail_qty: number;
  unclassified_qty: number;
  earliest_required_date: string | null;
  so_count: number;
  /** WHICH document says what they hold (F1). `stock_list` reads packed / unfinished;
   *  `proforma` is the newest un-converted PI standing in for a missing stock list (Q2);
   *  `none` means neither exists and the plan is built on demand alone. */
  holding_source: 'stock_list' | 'proforma' | 'none';
  /** The one figure the "They hold" cell shows: packed on a stock-list row, the invoiced
   *  quantity on a proforma row. Null - never 0 - when neither document names it. */
  holding_qty: number | null;
  holding_as_of: string | null;
  /** The stock list's own two figures. Both 0 on a proforma row: a proforma states one
   *  quantity per line and there is no unfinished half of it to report. */
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

/** One site pool (BRW / MWH / WH3 / DC1 / RSW), for the row popover's location table. */
export interface ContainerRequestSite {
  warehouse_code: string;
  on_hand: number;
  incoming_spo: number;
}

/** What the pool predicate left out, aggregated: the group locations feeding project orders. */
export interface ContainerRequestGroupLocations {
  count: number;
  on_hand: number;
  incoming_spo: number;
  /** A few codes to name the group, longest-holding first - never the whole list. */
  warehouse_codes: string[];
}

/** One packing-list shipment carrying this product, unreceived. `shipment_number` is null on
 *  a draft that has not been numbered yet. */
export interface ContainerRequestIncomingShipment {
  shipment_id: string;
  shipment_number: string | null;
  estimated_arrival_date: string | null;
  qty: number;
}

/** One outstanding PO line for this product - context in the popover, never netted. */
export interface ContainerRequestPoLine {
  po_number: string | null;
  expected_date: string | null;
  qty: number;
}

/** One open SO line behind a demand row - `include_lines=true` on the build. Flat, so the FE
 *  can bucket them into a schedule matrix or answer "which order does this cover" without a
 *  second fetch. `sum(qty per product) === that row's open_so_need`: since R15 both channels
 *  are the sales-order BOOK, told apart by `demand_class`, and a project line is listed at the
 *  remainder left after what CS already placed on a PO or an SPO. */
export interface ContainerRequestSoLine {
  product_id: string;
  item_code: string | null;
  so_number: string | null;
  customer_label: string | null;
  /** The project this order was published for. Null on a retail order, and on an adopted
   *  project order, which carries no registration at all. */
  project_title: string | null;
  /** Who sold it: the person when the agent row names one, the AutoCount agent code when it
   *  does not. Null when the order names no agent. */
  agent_label: string | null;
  /** What the customer pays for this line, in ringgit. Null when the sales book said nothing:
   *  a price of 0 would claim the line was free. */
  unit_price: number | null;
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
  /** The proforma standing in for a missing stock list, so the strip can say "PI 31/07"
   *  (AC-A2). Null whenever a stock list exists - it is then not consulted. */
  proforma_as_of: string | null;
  proforma_pi_number: string | null;
}

export interface ContainerRequestBuild {
  /** The plan row this build belongs to (R2): supplier and cut-off are read off it, and the
   *  typed quantities in `line_edits` are already applied to every `suggested_qty` below. */
  plan: LoadingPlanRecord;
  supplier_id: string;
  /** Null when this supplier has no stock list applied yet. NOT an empty state since F1: the
   *  plan builds from `product_suppliers` and the open order book regardless, and "They hold"
   *  reads the stand-in proforma or a dash. */
  stock_list_as_of: string | null;
  rows: ContainerRequestRow[];
  sources: ContainerRequestSources;
  /** Present when the build was called with `include_lines=true` (always, from this FE). */
  lines?: ContainerRequestSoLine[];
  /** "Plan until" (captain, 20 Aug) - the cutoff actually applied, echoed back so the FE
   *  never has to trust its own state alone for what the numbers on screen mean. Null when
   *  none was asked for. */
  plan_horizon_date: string | null;
}

export async function buildContainerRequest(planId: string): Promise<ContainerRequestBuild> {
  const res = await apiFetch('/api/v1/scm/container-requests/build?include_lines=true', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ plan_id: planId }),
  });
  return readJson<ContainerRequestBuild>(res, 'Failed to work out what to ask this supplier for');
}

/**
 * Sales history behind a loading-plan row: what was ORDERED, per product, per month, over the
 * last 12 full months, in two series (project and retail).
 *
 * A SIDECAR rather than a column on the build, because it is asked for the visible page's
 * products only - a supplier with 120 products would otherwise pay 240 monthly series on every
 * refresh for the 25 rows anybody is looking at.
 *
 * "Ordered", never "sold": the source is the sales-order book (`sales_order_lines.qty_ordered`
 * by `sales_orders.order_date`), so a booked order counts from the day it was booked whether
 * or not it has shipped.
 *
 * ── BACKEND CONTRACT (app/api/v1/scm/container_requests.py) ────────────────
 *  GET /api/v1/scm/container-requests/history?supplier_id=&product_ids=&product_ids=
 *      -> 200 ContainerRequestHistory. Auth: `scm.dashboard.view`.
 */
export interface ContainerRequestHistoryPoint {
  /** `YYYY-MM`. Twelve of them, zero-filled, oldest first. */
  month: string;
  qty: number;
}

export interface ContainerRequestHistorySeries {
  months: ContainerRequestHistoryPoint[];
  total: number;
  /** Mean over the twelve buckets, zeros included. */
  avg: number;
  /** Null when the series is empty - there is no peak of nothing. */
  peak_month: string | null;
  peak_qty: number;
}

export interface ContainerRequestHistoryProduct {
  product_id: string;
  project: ContainerRequestHistorySeries;
  retail: ContainerRequestHistorySeries;
}

export interface ContainerRequestHistory {
  /** First and last bucket, so the FE never has to work out which twelve months these are. */
  from_month: string;
  to_month: string;
  products: ContainerRequestHistoryProduct[];
}

export async function getContainerRequestHistory(
  supplierId: string,
  productIds: string[],
): Promise<ContainerRequestHistory> {
  const params = new URLSearchParams({ supplier_id: supplierId });
  for (const id of productIds) params.append('product_ids', id);
  const res = await apiFetch(`/api/v1/scm/container-requests/history?${params.toString()}`);
  return readJson<ContainerRequestHistory>(res, 'Failed to load the sales history');
}

/**
 * One reviewed line. It names a product OR one of our product sets, never both (R19).
 *
 * A set line carries no product id at all: the supplier sells the whole WC under a code our
 * catalogue does not hold, so the ask goes out under the set code, and naming one member
 * here would make the document disagree with the row it came from.
 */
export type ContainerRequestLine = { qty: number } & (
  | { product_id: string; product_set_id?: undefined }
  | { product_set_id: string; product_id?: undefined }
);

export async function sendContainerRequest(
  planId: string,
  lines: ContainerRequestLine[],
): Promise<{ notices: SupplierNotice[]; document_filename: string }> {
  const res = await apiFetch('/api/v1/scm/container-requests', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ plan_id: planId, lines }),
  });
  return readJson(res, 'Failed to send the request to the supplier');
}

/**
 * The request as a file for the quantities currently on screen, WITHOUT sending it (R23).
 *
 * The gear menu's "Download XLSX" / "Download PDF". `POST` because the lines are the body -
 * they are Ms Tee's edits, not a stored plan the server could re-derive - and because nothing
 * is created it sits behind the same read permission the build does. The name comes off the
 * server's `Content-Disposition` so the file and the sheet inside it agree on which supplier
 * and which day this is.
 */
export async function downloadContainerRequestDocument(
  planId: string,
  lines: ContainerRequestLine[],
  format: 'xlsx' | 'pdf',
): Promise<void> {
  const res = await apiFetch(`/api/v1/scm/container-requests/document?format=${format}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ plan_id: planId, lines }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to build the document'));
  const filename =
    filenameFromContentDisposition(res.headers.get('Content-Disposition')) ??
    `container-request.${format}`;
  saveBlobAs(await res.blob(), filename);
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

/**
 * "Create SPO" - a shipment line's PACKED quantity (`quantity_shipped`, never the PI's
 * invoiced one) becomes a real CRM purchase order line, PULLED from open PO line(s)
 * (`PLAN-scm-proforma-to-spo.md`'s Amendment, second decision: "Separate button after
 * packing-list apply").
 *
 * ── DOCTRINE CORRECTION (captain, 21 Aug) - the arithmetic was inverted ─────
 * His own words: "when there is PO, then we only can do SPO... it is when we got PO, then we
 * only can pull from the PO to form SPO." Every version before this treated an open PO as
 * competing supply that REDUCED the suggested SPO qty. Backwards: an SPO is the SHIPMENT LEG
 * of an existing PO - forming one PULLS quantity FROM open PO lines, and the pull IS the
 * SPO's composition, not a deduction from it.
 *
 *   * `suggested_qty` IS `po_covered_qty` - what the SAME earliest-first `po_takes` cascade
 *     as before (soonest `expected_date`, then PO number) pulls, capped at the packed qty.
 *     Never a remainder after PO/stock is subtracted.
 *   * `on_hand` / `incoming_spo` are CONTEXT ONLY - shown, never netted.
 *   * `no_po_qty = max(packed_qty - po_covered_qty, 0)` - the portion nothing open can back.
 *     When `po_covered_qty` is zero, the WHOLE line is `cannot_convert` (same shape as the
 *     no-supplier case, unselectable) with `reason` "No PO to pull from - raise the PO in
 *     AutoCount first."; a PARTIALLY-backed line stays selectable at `po_covered_qty`, with
 *     the shortfall named on `reason` too.
 *   * `covered` is GONE - it meant "nothing left to ask for", a concept that only existed
 *     when a PO was a deduction.
 *
 * ── BACKEND CONTRACT (app/api/v1/scm/fulfilment.py) ─────────────────────────
 *  GET  /api/v1/scm/inbound-shipments/{id}/spo-suggestion -> 200 SpoSuggestion. Auth:
 *       `scm.dashboard.view`. `already_converted: true` when this shipment already has
 *       SPOs from a prior run - `lines` is empty and `existing_spos` names them instead.
 *  POST /api/v1/scm/inbound-shipments/{id}/spo -> 201 SpoCreateResult. Body:
 *       { lines: [{shipment_line_id, qty, include, location_splits}] } - EVERY line on the
 *       shipment, ticked or not. `qty`/`location_splits` are RE-VALIDATED server-side against
 *       LIVE PO data, never trusted off an earlier `suggest` read - a line whose pull shrinks
 *       to zero between the two calls is skipped, not overdrawn. 409 when this shipment was
 *       already converted (names the existing SPOs). Auth: `scm.reorder.run` (a PO-book
 *       write, same permission the packing-list apply and PI-convert paths use).
 *  GET  /api/v1/scm/inbound-shipments/{id}/spo-worksheet/export -> 200 .xlsx bytes. The
 *       AutoCount handoff - what to key, per supplier. 404 until "Create SPO" has run.
 *
 * One SPO per SUPPLIER represented on the shipment - a container is routinely several
 * factories, and AutoCount POs are per supplier too. A line with no supplier recorded (the
 * n8n PDF path), or with nothing pullable from any open PO, cannot convert.
 *
 * **Recording the pull, and the honesty decision the plan asked to settle.** `create`
 * ADVANCES the source PO line's own `qty_received` by what it pulls (the IDENTICAL write
 * `allocation_suggestion_service.approve` already makes for a shipment drawing down a PO
 * line) - never link-only, which would double-count the same goods in `po_ordered_v` for
 * however long AutoCount reconciliation takes. `unwind` (below) reverses this exactly.
 *
 * ── SECOND AMENDMENT (captain, 21 Aug 00:40) - the planner table ────────────
 * The surface moved to `/procurement-management/packing-lists/{id}` (the planner tab), and
 * the shape moved from a checkbox list to a loading-plan-style table (`SpoPlannerTable`,
 * visual precedent `ContainerRequestSection`). `suggest`'s payload:
 *
 *   * `po_takes` - the `po_covered_qty` total broken into the per-PO takes an EARLIEST-FIRST
 *     cascade makes (soonest `expected_date`, then PO number) - the same discipline
 *     Place-on-PO's cascade embodies. Each take also names the PO's OWN date and supplier
 *     (doctrine-correction ask - a pinned match can resolve to a differently-spelled
 *     supplier than the shipment line's own).
 *   * `location_options` + `suggested_warehouse_id` - candidate destination warehouses for
 *     this product, each with its outstanding SO, on hand, incoming SPO and the individual
 *     `demand_lines` behind that SO figure (doctrine-correction ask, "what SO am I
 *     covering"), ranked by the shared Fulfilment Priority policy (project earlier delivery
 *     first, then retail). The "after figure" (what a location's `available` becomes once
 *     this SPO lands there) is computed on screen as `available + <the edited SPO qty>`,
 *     never sent stale from the server - the qty is live-edited on this same screen.
 *
 * ── FOURTH ASK (doctrine correction, same message) - multi-location split ───
 * "I can create SPO to multiple locations." `SpoConfirmLine.warehouse_id` (singular) is
 * replaced by `location_splits: {warehouse_id, qty}[]` - zero, one or several destinations
 * for ONE line's SPO qty, validated server-side to sum to exactly what that line pulls.
 * Each split writes its own `spo_allocations` row in the SAME confirm - one confirm, still
 * one write per DECISION, now zero-or-many decisions per line rather than zero-or-one.
 * `SpoCreateResult.allocations` names every row written, across every split.
 *
 * ── THIRD AMENDMENT (captain live case, 21 Aug) - delete + self-heal ────────
 * He created SPOs, then deleted their `spo_allocations` on the SPO Allocations screen, and
 * the planner stayed stuck on "SPO already created" with no way back. Two additions:
 *
 *  DELETE /api/v1/scm/inbound-shipments/{id}/spo -> 200 SpoDeleteResult. Auth: `scm.reorder.
 *       run` (same as create). Unwinds the whole conversion for this shipment - every
 *       `purchase_orders` header it minted, their lines, the `shipment_line_spo_link` rows,
 *       any `spo_allocations` left hanging off those PO lines, AND (doctrine correction)
 *       REVERSES the `qty_received` advance `create` made on every source PO line those
 *       lines pulled from (`restored_po_line_count`). 409 (`not_crm_spo`) when a linked
 *       header was not created by Create SPO (an AutoCount import) - refused, not skipped.
 *       404 when this shipment has no SPO to delete. Exposed on the planner as the Delete
 *       action on the already-converted state.
 *  `SpoSuggestion.self_heal_note` - non-null only when THIS `spo-suggestion` call actually
 *       cleaned up a link left behind by a CRM SPO removed some OTHER way than the DELETE
 *       above (a generic PO delete, a bad migration) - shown as a small informational note,
 *       never a toast, since it describes something that already happened silently. That
 *       bypass path does NOT reverse the source PO's advance (only `unwind` does), so a
 *       self-healed line can come back `cannot_convert` rather than restored - a documented
 *       limitation, not a bug.
 */
export type SpoMatchedBy = 'po_ref' | 'product' | null;

/** One EARLIEST-FIRST cascade take behind `po_covered_qty`. */
export interface SpoPoTake {
  po_line_id: string;
  po_number: string;
  qty: number;
  expected_date: string | null;
  /** The PO's OWN document date - distinct from `expected_date` (when the line is due). */
  po_date: string | null;
  /** The PO's OWN supplier - can differ from the shipment line's own supplier on a pinned
   *  match resolved to a differently-spelled book entry (fourth amendment). */
  supplier_name: string | null;
  /** What this PO LINE has open, not what the cascade took from it. Unticking another take
   *  re-runs the walk over the lines still ticked, and `qty` alone cannot answer that: a
   *  line that gave 40 while its neighbour was ticked may have 150 to give without it. */
  open_qty: number;
}

/** One open SO line behind a location's `outstanding_so` - "what SO am I covering"
 *  (doctrine-correction ask), earliest need date first. */
export interface SpoDemandLine {
  so_number: string | null;
  customer_name: string | null;
  agent_name: string | null;
  required_date: string | null;
  order_date: string | null;
  qty: number;
}

/**
 * One piece of demand this SPO could cover, tickable (Q4, AC-G3).
 *
 * Two families, because they are two different records: PROJECT demand is an unlinked
 * order-inquiry row (part 2 P3), and RETAIL demand is a line of the sales-order book. Only
 * the project side can carry a link afterwards - the links table hangs off the inquiry row -
 * so `kind` is not decoration, it is which half of the pipeline this line lives in.
 */
export interface SpoCoverageLine {
  /** `project:<row id>` / `retail:<so line id>` - stable, and what `so_line_ids` sends. */
  key: string;
  kind: 'project' | 'retail';
  document: string | null;
  customer_name: string | null;
  required_date: string | null;
  /** What this piece of demand still needs. */
  qty: number;
  /** Where it is needed. Null on a project row whose stock location names no warehouse we
   *  hold - it still ticks, it just cannot steer the split. */
  warehouse_id: string | null;
  warehouse_code: string | null;
  /** Pre-ticked by the default walk: project by required date, then retail by required
   *  date, until the packed quantity is used up (Q4). */
  default_ticked: boolean;
}

/** One candidate destination warehouse for a line's SPO qty, ranked. */
export interface SpoLocationOption {
  warehouse_id: string;
  warehouse_code: string | null;
  outstanding_so: number;
  on_hand: number;
  incoming_spo: number;
  /** Signed, never clamped - `on_hand - outstanding_so + incoming_spo`. Add the qty being
   *  proposed for this location to get the "after" figure the plan asks for. */
  available: number;
  /** Fulfilment Priority score, absent on a location with no open demand behind it - those
   *  sort after every ranked one, by `warehouse_code`. */
  rank_score: number | null;
  /** The individual demand lines behind `outstanding_so`, earliest first - cascade these
   *  against the live SPO qty landing HERE to answer "what SO am I covering". */
  demand_lines: SpoDemandLine[];
}

export interface SpoSuggestionLine {
  shipment_line_id: string;
  product_id: string;
  item_code: string | null;
  product_name: string | null;
  supplier_id: string | null;
  supplier_name: string | null;
  packed_qty: number;
  po_covered_qty: number;
  matched_po_number: string | null;
  matched_by: SpoMatchedBy;
  /** Earliest-first breakdown of `po_covered_qty` - empty when nothing is pullable. */
  po_takes: SpoPoTake[];
  /** Context only since the doctrine correction - never netted into `suggested_qty`. */
  on_hand: number;
  incoming_spo: number;
  /** `po_covered_qty`, capped at `packed_qty` by the cascade - what the PO(s) PULL this SPO
   *  up to. Editable, but cannot exceed `po_covered_qty` (nothing more to pull). */
  suggested_qty: number;
  /** `max(packed_qty - po_covered_qty, 0)` - the portion nothing open can back. Shown as
   *  context on a selectable line; the reason the WHOLE line is `cannot_convert` when it
   *  equals `packed_qty`. */
  no_po_qty: number;
  /** No supplier recorded, OR nothing at all is pullable from an open PO - cannot become an
   *  SPO line, like the no-supplier case. */
  cannot_convert: boolean;
  /** Why `cannot_convert`, or a note about a partially-uncovered remainder. Null on a line
   *  fully backed by an open PO. */
  reason: string | null;
  unit_cost: number | null;
  currency: string | null;
  /** Candidate destinations for this line's SPO qty, ranked - empty on a line that cannot
   *  convert. */
  location_options: SpoLocationOption[];
  suggested_warehouse_id: string | null;
  /** The demand this SPO can be pointed at, in the order the default ticks walk it: project
   *  by required date, then retail by required date (Q4, AC-G3). */
  so_coverage: SpoCoverageLine[];
}

export interface SpoRef {
  purchase_order_id: string;
  po_number: string | null;
  supplier_id: string | null;
  supplier_name: string | null;
}

export interface SpoSuggestion {
  shipment_id: string;
  shipment_number: string | null;
  shipment_status: string | null;
  /** True when this shipment already has SPOs from a prior "Create SPO" - `lines` is empty
   *  and the caller shows `existing_spos` instead of a confirm screen. */
  already_converted: boolean;
  existing_spos: SpoRef[];
  lines: SpoSuggestionLine[];
  /** Non-null only when this call self-healed a stale link (a CRM SPO removed some way
   *  other than the DELETE below) - see the module docstring's third amendment. */
  self_heal_note: string | null;
}

/** One destination for a slice of a line's SPO qty - the fourth amendment's multi-location
 *  split. All of a line's splits must sum to exactly what that line pulls. */
export interface SpoLocationSplit {
  warehouse_id: string;
  qty: number;
}

export interface SpoConfirmLine {
  shipment_line_id: string;
  qty: number;
  include: boolean;
  /** Zero, one or several destinations (fourth amendment) - empty writes no allocation for
   *  this line, same as every call before this ask. */
  location_splits?: SpoLocationSplit[];
  /** Which PO takes to draw from (AC-G1). Absent means every take the server re-derives;
   *  present means ONLY these, and the SPO quantity falls to what they cover (AC-G2). */
  po_take_ids?: string[];
  /** Which demand this SPO is being pointed at - `SpoCoverageLine.key`s (AC-G3). Drives the
   *  location split on screen, and the link rows the create writes for the project half. */
  so_line_ids?: string[];
}

export interface CreatedSpo extends SpoRef {
  currency: string | null;
  lines: number;
  qty: number;
}

/** One `spo_allocations` row `create` wrote alongside its SPO line. */
export interface SpoAllocationWritten {
  shipment_line_id: string;
  warehouse_id: string;
  allocation_id: string;
  qty: number;
}

/** One link the create wrote from a ticked project row to the SPO allocation covering it. */
export interface SpoDemandLink {
  key: string;
  document: string | null;
  spo_number: string | null;
  qty: number;
}

export interface SpoCreateResult {
  shipment_id: string;
  shipment_number: string | null;
  created_spos: CreatedSpo[];
  skipped: { shipment_line_id: string; item_code: string | null; reason: string }[];
  allocations: SpoAllocationWritten[];
  /** The project rows this SPO was tied to (AC-G6). Retail ticks steer the split and the
   *  clamp but write no link: the links table hangs off an order-inquiry row, and a retail
   *  sales-order line has none. */
  demand_links: SpoDemandLink[];
}

export async function getSpoSuggestion(shipmentId: string): Promise<SpoSuggestion> {
  const res = await apiFetch(`/api/v1/scm/inbound-shipments/${shipmentId}/spo-suggestion`);
  return readJson<SpoSuggestion>(res, 'Failed to work out what this container still needs an SPO for');
}

export async function createSpo(
  shipmentId: string,
  lines: SpoConfirmLine[],
): Promise<SpoCreateResult> {
  const res = await apiFetch(`/api/v1/scm/inbound-shipments/${shipmentId}/spo`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lines }),
  });
  return readJson<SpoCreateResult>(res, 'Failed to create the SPO');
}

/** The result of the Delete action on an already-converted planner row. */
export interface SpoDeleteResult {
  shipment_id: string;
  shipment_number: string | null;
  deleted_po_numbers: string[];
  deleted_spo_count: number;
  deleted_allocation_count: number;
  /** Source PO lines whose `qty_received` advance was reversed (doctrine correction). */
  restored_po_line_count: number;
}

export async function deleteSpo(shipmentId: string): Promise<SpoDeleteResult> {
  const res = await apiFetch(`/api/v1/scm/inbound-shipments/${shipmentId}/spo`, {
    method: 'DELETE',
  });
  return readJson<SpoDeleteResult>(res, 'Failed to delete the SPO');
}

export async function downloadSpoWorksheet(
  shipmentId: string,
  fallbackName?: string | null,
): Promise<void> {
  const res = await apiFetch(`/api/v1/scm/inbound-shipments/${shipmentId}/spo-worksheet/export`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to export the SPO worksheet'));
  const filename =
    filenameFromContentDisposition(res.headers.get('Content-Disposition')) ??
    `${fallbackName || 'container'}-spo-worksheet.xlsx`;
  saveBlobAs(await res.blob(), filename);
}
