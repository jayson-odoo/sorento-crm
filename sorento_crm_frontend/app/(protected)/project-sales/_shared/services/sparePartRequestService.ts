import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import { codeWithName } from '@/lib/product-display';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';

/**
 * SPARE-PART-ORDER-REQUEST (`PLAN-spare-part-order-request-12nov.md`). The request IS an
 * order inquiry of type `spare_part_request`; the OI page reads it through
 * `orderInquiryService`, this file holds its own moves.
 *
 * ── BACKEND CONTRACT (app/api/v1/projects/spare_part_requests.py) ──────────
 *  POST   /api/v1/project-sales/spare-part-requests                     body -> 201 detail
 *  GET    /api/v1/project-sales/spare-part-requests/{id}                -> detail
 *  PUT    /api/v1/project-sales/spare-part-requests/{id}                body -> detail
 *  POST   /api/v1/project-sales/spare-part-requests/{id}/submit         -> detail
 *  PATCH  /api/v1/project-sales/spare-part-requests/{id}/lines/{rowId}  {qty?, unit_price?}
 *  POST   /api/v1/project-sales/spare-part-requests/{id}/approve        {note?}
 *  POST   /api/v1/project-sales/spare-part-requests/{id}/reject         {reason}
 *  POST   /api/v1/project-sales/spare-part-requests/{id}/revise
 *  Auth: `procurement.spare_part_requests.create` for the requester's moves; approve,
 *  reject and line edits are the current approval stage's team (or an admin), never the
 *  requester, checked on the server.
 */

const BASE = '/api/v1/project-sales/spare-part-requests';

export interface SparePartLineInput {
  /** An existing line keeps its id (and its photos) when the form is saved again. */
  id?: string | null;
  product_id: string | null;
  stock_location: string | null;
  qty: string | null;
  unit_price: string | null;
}

export interface SparePartRequestInput {
  currency: string | null;
  needed_by: string | null;
  default_location: string | null;
  reason: string | null;
  lines: SparePartLineInput[];
}

export interface SparePartLine {
  id: string;
  product_id: string | null;
  product_name?: string | null;
  item_code: string | null;
  description: string | null;
  stock_location: string | null;
  qty: string;
  /** The prices are supplier cost: null for a reader who may not see them. */
  unit_price: string | null;
  total: string | null;
  requested_qty: string | null;
  requested_unit_price: string | null;
  state: string;
  ack_state?: string | null;
  /** Photos added / removed on this line since the request was last submitted. */
  photo_changes?: { added: number; removed: number };
}

export interface SparePartRequest {
  id: string;
  inquiry_no: string | null;
  inquiry_type: 'spare_part_request';
  state: string;
  currency: string | null;
  needed_by: string | null;
  default_location: string | null;
  reason: string | null;
  requested_by_name?: string | null;
  submitted_at?: string | null;
  approved_at?: string | null;
  approved_by_name?: string | null;
  reject_reason?: string | null;
  can_decide: boolean;
  can_edit: boolean;
  can_revise: boolean;
  total: string | null;
  lines: SparePartLine[];
}

/** A 422 from the server names the field it is about (`details.field`). */
export class SparePartRequestError extends Error {
  field?: string;
  constructor(message: string, field?: string) {
    super(message);
    this.field = field;
  }
}

async function readError(response: Response, fallback: string): Promise<SparePartRequestError> {
  const clone = response.clone();
  const message = await extractApiError(response, fallback);
  let field: string | undefined;
  try {
    const body = (await clone.json()) as { detail?: { details?: { field?: string } } };
    field = body?.detail?.details?.field;
  } catch {
    field = undefined;
  }
  return new SparePartRequestError(message, field);
}

async function send<T>(url: string, init: RequestInit, fallback: string): Promise<T> {
  const response = await apiFetch(url, init);
  if (!response.ok) throw await readError(response, fallback);
  return (await response.json()) as T;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export function getSparePartRequest(id: string): Promise<SparePartRequest> {
  return send(`${BASE}/${id}`, { method: 'GET' }, 'Failed to load the spare part request');
}

export function createSparePartRequest(body: SparePartRequestInput): Promise<SparePartRequest> {
  return send(BASE, json('POST', body), 'Failed to save the spare part request');
}

export function updateSparePartRequest(
  id: string,
  body: SparePartRequestInput,
): Promise<SparePartRequest> {
  return send(`${BASE}/${id}`, json('PUT', body), 'Failed to save the spare part request');
}

export function submitSparePartRequest(id: string): Promise<SparePartRequest> {
  return send(`${BASE}/${id}/submit`, json('POST'), 'Failed to submit the spare part request');
}

export function editSparePartLine(
  id: string,
  rowId: string,
  edit: { qty?: string; unit_price?: string },
): Promise<SparePartRequest> {
  return send(`${BASE}/${id}/lines/${rowId}`, json('PATCH', edit), 'Failed to change the line');
}

export function approveSparePartRequest(id: string, note?: string): Promise<SparePartRequest> {
  return send(`${BASE}/${id}/approve`, json('POST', { note: note || null }), 'Failed to approve');
}

export function rejectSparePartRequest(id: string, reason: string): Promise<SparePartRequest> {
  return send(`${BASE}/${id}/reject`, json('POST', { reason }), 'Failed to reject');
}

export function reviseSparePartRequest(id: string): Promise<SparePartRequest> {
  return send(`${BASE}/${id}/revise`, json('POST'), 'Failed to revise');
}

/** The catalogue, searched on the server by code and name (UAC R2), one page at a time. */
export async function searchSparePartProducts(
  query: string,
  pageIndex = 0,
): Promise<SearchableSelectOption[]> {
  const search = buildDataGridParams(
    { pageIndex: 0, pageSize: 50, sorting: [], searchQuery: query.trim() },
    { offset: pageIndex * 50 },
  );
  const response = await apiFetch(`/api/v1/master-data/products/select?${search.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load products'));
  const body = (await response.json()) as {
    data?: { id: string; product_code: string; product_name: string }[];
  };
  return (Array.isArray(body?.data) ? body.data : []).map((p) => ({
    value: String(p.id),
    label: codeWithName(p.product_code, p.product_name, ' · '),
    code: p.product_code,
    name: p.product_name,
    searchText: `${p.product_code} ${p.product_name}`,
  }));
}

/** Active locations, by code (a line's `stock_location` is the warehouse code). */
export async function getSparePartLocations(): Promise<SearchableSelectOption[]> {
  const search = buildDataGridParams(
    { pageIndex: 0, pageSize: 200, sorting: [{ id: 'warehouse_code', desc: false }], searchQuery: '' },
    { is_active: true },
  );
  const response = await apiFetch(`/api/v1/inventory/warehouses?${search.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load locations'));
  const body = (await response.json()) as {
    data?: { warehouse_code: string; warehouse_name?: string | null }[];
  };
  return (Array.isArray(body?.data) ? body.data : []).map((w) => ({
    value: w.warehouse_code,
    label: w.warehouse_name ? `${w.warehouse_code} · ${w.warehouse_name}` : w.warehouse_code,
  }));
}
