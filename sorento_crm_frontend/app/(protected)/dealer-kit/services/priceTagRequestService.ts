/**
 * CRM-side price tag request service.
 *
 * Calls `/api/v1/dealer-kit/price-tag-requests` via `apiFetch`.
 */

import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { LineTagData, TagSheetDoc } from '@/lib/dealer-kit/tag-template-types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type PriceTagLineType = 'product' | 'product_set';

export interface PriceTagRequestLine {
  id: string;
  line_type: PriceTagLineType;
  product_id: string | null;
  product_set_id: string | null;
  name: string;
  code: string;
  show_promo_price: boolean;
  quantity: number;
  alternatives: { product_id: string; name: string; code: string }[];
  included_accessories: string | null;
  sort_order: number;
  marketing_price_override: number | null;
  marketing_override_reason: string | null;
  /** Resolved list price. */
  list_price: number | null;
  /** Resolved selling price. */
  sell_price: number | null;
}

/**
 * The shape `entity_attachment_service.list_attachments_for_entity` answers
 * with - the SAME shape the portal's own detail route carries (D49, S1), so
 * this and the portal's `PortalAttachment` type must never drift apart again.
 * No `id` field: `link_id` is the row identity (what a key/unlink target
 * reads), `attachment_id` is what the download route is keyed on - the two
 * are NOT interchangeable.
 */
export interface PriceTagAttachment {
  link_id: string;
  attachment_id: string;
  filename: string | null;
  size: number | null;
  url: string | null;
  content_type: string | null;
  uploaded_at: string | null;
  uploader_kind: 'user' | 'contact' | 'system' | null;
  uploaded_by_name: string | null;
  uploaded_by_role: 'contact' | 'staff' | 'unknown';
  can_unlink: boolean;
}

export interface PriceTagRequestSummary {
  id: string;
  doc_number: string;
  debtor_code: string | null;
  /** Null while the portal request is still a draft (D48a). */
  debtor_name: string | null;
  promotion_id: string | null;
  promotion_name: string | null;
  needed_by_date: string | null;
  notes: string | null;
  status: string;
  line_count: number;
  created_at: string;
  assigned_to_id: string | null;
  assigned_to_name: string | null;
  contact_name: string | null;
}

export interface PriceTagRequestDetail extends PriceTagRequestSummary {
  contact_id: string;
  lines: PriceTagRequestLine[];
  attachments?: PriceTagAttachment[];
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const BASE = '/api/v1/dealer-kit/price-tag-requests';

// ---------------------------------------------------------------------------
// API surface
// ---------------------------------------------------------------------------

export interface PriceTagRequestListParams {
  page: number;
  limit: number;
  sort?: string;
  dir?: 'asc' | 'desc';
  query?: string;
  status?: string;
}

export interface PriceTagRequestListResult {
  data: PriceTagRequestSummary[];
  pagination: { total: number; page: number; limit: number };
}

export async function listPriceTagRequests(
  params: PriceTagRequestListParams,
): Promise<PriceTagRequestListResult> {
  // Through `buildDataGridParams`, which is the one place page/limit/sort/dir/
  // query are spelled. The list and the record pager both call this with the
  // page-number shape, so it is translated here rather than in two callers.
  const usp = buildDataGridParams(
    {
      pageIndex: params.page - 1,
      pageSize: params.limit,
      sorting: params.sort
        ? [{ id: params.sort, desc: params.dir === 'desc' }]
        : [],
      searchQuery: params.query ?? '',
    },
    { status: params.status },
  );

  const response = await apiFetch(`${BASE}?${usp.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load price tag requests'));
  }

  // The page and the true total, both counted by the server. This used to fetch
  // the WHOLE table and sort and slice it here, so every keystroke shipped every
  // request in the system and the record count under the grid was the length of
  // the array that happened to arrive.
  const body: {
    data: PriceTagRequestSummary[];
    pagination: { total: number; page: number; limit: number };
  } = await response.json();

  return {
    data: body.data ?? [],
    pagination: {
      total: body.pagination?.total ?? 0,
      page: body.pagination?.page ?? params.page,
      limit: body.pagination?.limit ?? params.limit,
    },
  };
}

export async function getPriceTagRequest(
  id: string,
): Promise<PriceTagRequestDetail | null> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}`);
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load price tag request'));
  }
  return response.json();
}

export async function claimPriceTagRequest(
  id: string,
): Promise<PriceTagRequestDetail> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}/claim`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to claim request'));
  }
  return response.json();
}

export async function transitionPriceTagRequest(
  id: string,
  action: string,
): Promise<PriceTagRequestDetail> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}/transition`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: action }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to transition request'));
  }
  return response.json();
}

// ---------------------------------------------------------------------------
// Line update
// ---------------------------------------------------------------------------

export async function updateRequestLine(
  requestId: string,
  lineId: string,
  data: { marketing_price_override?: number | null; marketing_override_reason?: string | null },
): Promise<PriceTagRequestLine> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(requestId)}/lines/${encodeURIComponent(lineId)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to update line'));
  }
  return response.json();
}

// ---------------------------------------------------------------------------
// Tag sheet design (S4)
// ---------------------------------------------------------------------------

export async function getTagSheetDoc(
  requestId: string,
): Promise<TagSheetDoc | null> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(requestId)}/design`,
  );
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load tag sheet design'));
  }
  const result: { page_id: string; version: number; doc: TagSheetDoc | null } =
    await response.json();
  return result.doc ?? null;
}

export async function saveTagSheetDoc(
  requestId: string,
  doc: TagSheetDoc,
): Promise<void> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(requestId)}/design`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ doc }),
    },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save tag sheet design'));
  }
}

/**
 * Display data for this request's lines, resolved by the backend.
 *
 * ```
 * POST /api/v1/dealer-kit/price-tag-requests/{id}/resolve-prices
 *   body: string[] | null   line ids, or null for every line
 *   200 [{ line_id, code, name, dimensions, spec_lines, set_members, images[],
 *          list_price, sell_price, show_promo_price, included_accessories,
 *          quantity }]
 * ```
 *
 * Prices resolve at render time through the pricing engine and are never stored
 * in the tag sheet document (ADR 0008). A marketing override on the line wins
 * over the resolved offer, which is why this is resolved per LINE rather than
 * per product.
 */
export async function resolveRequestLines(
  requestId: string,
  lineIds?: string[],
): Promise<LineTagData[]> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(requestId)}/resolve-prices`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(lineIds ?? null),
    },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to resolve line prices'));
  }
  return response.json();
}

// ---------------------------------------------------------------------------
// Export (S5)
// ---------------------------------------------------------------------------

export interface ExportResult {
  downloadId: string;
  status: string;
  filename: string | null;
}

export async function exportTagSheet(
  requestId: string,
  sheetIds?: string[],
): Promise<ExportResult> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(requestId)}/export`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sheet_ids: sheetIds ?? null }),
    },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to export tag sheet'));
  }
  return response.json();
}
