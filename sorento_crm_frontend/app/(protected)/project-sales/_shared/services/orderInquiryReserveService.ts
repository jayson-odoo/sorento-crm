import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

const BASE = '/api/v1/project-sales';

/**
 * Order inquiry: request CS to reserve stock (`PLAN-oi-request-cs-reserve.md` 3.2/3.3).
 *
 * A sibling of `orderInquiryService.ts`, its own file because this is a self-contained
 * sub-feature (request / cancel / reserve) rather than another verb on the row itself.
 */

export interface CreateReserveRequestRow {
  row_id: string;
  qty_requested: string | number;
  warehouse_id: string;
}

export interface CreateReserveRequestPayload {
  rows: CreateReserveRequestRow[];
  note?: string | null;
}

export interface OrderInquiryReserveRequestRow {
  id: string;
  row_id: string;
  item_code: string | null;
  qty_requested: string;
  warehouse_id: string | null;
  location: string | null;
  qty_reserved: string | null;
  reason: string | null;
}

export interface OrderInquiryReserveRequest {
  id: string;
  order_inquiry_id: string;
  ordinal: number;
  state: 'requested' | 'reserved' | 'cancelled';
  requested_by: string | null;
  requested_by_name: string | null;
  requested_at: string | null;
  note: string | null;
  reserved_by_name: string | null;
  reserved_at: string | null;
  cancelled_at: string | null;
  rows: OrderInquiryReserveRequestRow[];
  /** The first recipient the request mail actually named, for the dialog's own toast
   * (plan 3.7: "Request #2 sent to Eling"). Null when nobody is configured yet. */
  first_to_name: string | null;
}

/** Purchasing's own "Request CS to reserve" (AC-RS-1 to AC-RS-5). Quantities travel as
 * strings, as everywhere else in this domain - the caller may hand this a number (the
 * dialog's own number input), stringified here rather than trusted on the wire. */
export async function createOrderInquiryReserveRequest(
  inquiryId: string,
  payload: CreateReserveRequestPayload,
): Promise<OrderInquiryReserveRequest> {
  const requestBody = {
    ...payload,
    rows: payload.rows.map((row) => ({ ...row, qty_requested: String(row.qty_requested) })),
  };
  const response = await apiFetch(`${BASE}/order-inquiries/${inquiryId}/reserve-requests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestBody),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to send that reserve request'));
  const body = await response.json();
  return { ...body, first_to_name: body.notified_name ?? null };
}

/** The requester's own undo while nothing has been reserved yet (AC-RS-19). Mostly
 * reached through the deferred action `order_inquiry_reserve_request.cancel`; kept as a
 * plain call too for a caller that wants it immediate. */
export async function cancelOrderInquiryReserveRequest(
  requestId: string,
): Promise<OrderInquiryReserveRequest> {
  const response = await apiFetch(`${BASE}/order-inquiries/reserve-requests/${requestId}/cancel`, {
    method: 'POST',
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to cancel that reserve request'));
  const body = await response.json();
  return { ...body, first_to_name: body.notified_name ?? null };
}

export interface ReserveRowPayload {
  warehouse_id: string;
  qty_reserved: string | number;
  reason?: string | null;
}

export interface UnreserveRowPayload {
  qty: string | number;
  note?: string | null;
}

export interface OrderInquiryReserveHistoryEntry {
  kind: 'requested' | 'reserved' | 'unreserved' | 'cancelled' | string;
  qty: string | null;
  location: string | null;
  reason: string | null;
  actor_name: string | null;
  created_at: string | null;
}

/**
 * Eling's own Confirm, ONE ROW at a time (`PLAN-oi-request-cs-reserve.md` section 6c
 * F2 - supersedes the old all-rows `reserveOrderInquiryRequest`, whose own route is
 * deleted). Answers exactly one request row; the request itself stays `requested`
 * while any other row of it is still unanswered, `reserved` on the one that
 * completes it.
 */
export async function reserveOrderInquiryRow(
  requestId: string,
  rowId: string,
  payload: ReserveRowPayload,
): Promise<OrderInquiryReserveRequestRow> {
  const requestBody = { ...payload, qty_reserved: String(payload.qty_reserved) };
  const response = await apiFetch(
    `${BASE}/order-inquiries/reserve-requests/${requestId}/rows/${rowId}/reserve`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
    },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to confirm that reserve'));
  return response.json();
}

/** F5: gives back part (or all) of what was reserved on ONE row - its own action,
 * never Unlink. No email either way. */
export async function unreserveOrderInquiryRow(
  requestId: string,
  rowId: string,
  payload: UnreserveRowPayload,
): Promise<OrderInquiryReserveRequestRow> {
  const requestBody = { ...payload, qty: String(payload.qty) };
  const response = await apiFetch(
    `${BASE}/order-inquiries/reserve-requests/${requestId}/rows/${rowId}/unreserve`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
    },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to unreserve that row'));
  return response.json();
}

/** F3: one row's own history, newest first - the dialog's History tab. */
export async function getOrderInquiryRowHistory(
  requestId: string,
  rowId: string,
): Promise<OrderInquiryReserveHistoryEntry[]> {
  const response = await apiFetch(
    `${BASE}/order-inquiries/reserve-requests/${requestId}/rows/${rowId}/history`,
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load that history'));
  const body = await response.json();
  return Array.isArray(body) ? body : [];
}

/** Every reserve request this header has ever raised, newest first - used to find
 * a row's own open request (or last-answered one) for `ReserveRowDialog`. */
export async function getOrderInquiryReserveRequests(
  inquiryId: string,
): Promise<OrderInquiryReserveRequest[]> {
  const response = await apiFetch(`${BASE}/order-inquiries/${inquiryId}/reserve-requests`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load reserve requests'));
  const body = await response.json();
  return (Array.isArray(body) ? body : []).map((item: OrderInquiryReserveRequest) => ({
    ...item,
    first_to_name: null,
  }));
}
