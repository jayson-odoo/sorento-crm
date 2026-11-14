import type { SortingState } from '@tanstack/react-table';
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';

/**
 * SPARE-PART-ORDER-REQUEST (`PLAN-spare-part-order-request-12nov.md`). The request IS an
 * order inquiry of type `spare_part_request`; the OI page reads it through
 * `orderInquiryService`, this file holds its own moves.
 *
 * ── BACKEND CONTRACT (app/api/v1/projects/spare_part_requests.py) ──────────
 *  GET    /api/v1/project-sales/spare-part-requests                     ?page&limit&sort&dir&query&state[]
 *         -> { data: SparePartRequestListItem[], pagination } (own, decidable, admin: G3)
 *  POST   /api/v1/project-sales/spare-part-requests                     body -> 201 detail
 *  GET    /api/v1/project-sales/spare-part-requests/{id}                -> detail
 *  PUT    /api/v1/project-sales/spare-part-requests/{id}                body -> detail (while
 *         pending approval it restarts approval at the first level, G5)
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
  /** G1: what the requester calls this part; the server falls back to the product name. */
  description?: string | null;
  stock_location: string | null;
  qty: string | null;
  unit_price: string | null;
  /** SPARE-PART-OR-B C (C5.1): the line's own delivery date (YYYY-MM-DD); the header's when
   *  null. */
  delivery_date?: string | null;
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
  /** R2: the approved product; `product_id` is an open revision's while one swaps it. */
  approved_product_id?: string | null;
  product_name?: string | null;
  item_code: string | null;
  description: string | null;
  stock_location: string | null;
  /** C5.1: the line's delivery date (an open revision's, on the order request page). */
  delivery_date?: string | null;
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
  /** SPARE-PART-OR-B (U2.6): the OI- number from final approval; null before it. */
  oi_no?: string | null;
  inquiry_type: 'spare_part_request';
  state: string;
  /** U4.2: an open revision's state (draft / pending_approval / rejected), else null.
   *  While one is open `lines[].qty` is the revision's qty. */
  revision_state?: string | null;
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

/** One row of the spare part requests list (G3). */
export interface SparePartRequestListItem {
  id: string;
  inquiry_no: string | null;
  oi_no?: string | null;
  state: string;
  revision_state?: string | null;
  /** The open revision's state when there is one, else `state` (pill and filter). */
  effective_state?: string | null;
  currency: string | null;
  requested_by?: string | null;
  requested_by_name: string | null;
  needed_by: string | null;
  line_count: number;
  /** Null when the reader may not see the expected cost. */
  total: string | null;
  submitted_at: string | null;
}

export interface SparePartRequestListParams {
  pageIndex: number;
  pageSize: number;
  sorting: SortingState;
  searchQuery: string;
  states: string[];
}

export interface SparePartRequestListEnvelope {
  data: SparePartRequestListItem[];
  pagination: { total: number; page: number; limit: number };
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

export async function listSparePartRequests(
  params: SparePartRequestListParams,
): Promise<SparePartRequestListEnvelope> {
  const search = buildDataGridParams(params, { state: params.states });
  const response = await apiFetch(`${BASE}?${search.toString()}`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load order requests'));
  return (await response.json()) as SparePartRequestListEnvelope;
}

export function getSparePartRequest(id: string): Promise<SparePartRequest> {
  return send(`${BASE}/${id}`, { method: 'GET' }, 'Failed to load the order request');
}

export function createSparePartRequest(body: SparePartRequestInput): Promise<SparePartRequest> {
  return send(BASE, json('POST', body), 'Failed to save the order request');
}

export function updateSparePartRequest(
  id: string,
  body: SparePartRequestInput,
): Promise<SparePartRequest> {
  return send(`${BASE}/${id}`, json('PUT', body), 'Failed to save the order request');
}

export function submitSparePartRequest(id: string): Promise<SparePartRequest> {
  return send(`${BASE}/${id}/submit`, json('POST'), 'Failed to submit the order request');
}

export function editSparePartLine(
  id: string,
  rowId: string,
  edit: { qty?: string; unit_price?: string },
): Promise<SparePartRequest> {
  return send(`${BASE}/${id}/lines/${rowId}`, json('PATCH', edit), 'Failed to change the line');
}

/** `submittedAt` is the submission the approver's page rendered: the server answers 409 when
 *  the request was edited (approval restarted) since. */
export function approveSparePartRequest(
  id: string,
  note?: string,
  submittedAt?: string | null,
): Promise<SparePartRequest> {
  return send(
    `${BASE}/${id}/approve`,
    json('POST', { note: note || null, submitted_at: submittedAt ?? null }),
    'Failed to approve',
  );
}

export function rejectSparePartRequest(
  id: string,
  reason: string,
  submittedAt?: string | null,
): Promise<SparePartRequest> {
  return send(
    `${BASE}/${id}/reject`,
    json('POST', { reason, submitted_at: submittedAt ?? null }),
    'Failed to reject',
  );
}

export function reviseSparePartRequest(id: string): Promise<SparePartRequest> {
  return send(`${BASE}/${id}/revise`, json('POST'), 'Failed to revise');
}
