/**
 * CRM-side price tag request service.
 *
 * Calls `/api/v1/dealer-kit/price-tag-requests` via `apiFetch`.
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  TagSheetDoc,
  ResolvedTagData,
} from '@/lib/dealer-kit/tag-template-types';

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

export interface PriceTagAttachment {
  id: string;
  filename: string;
  content_type: string | null;
  url: string | null;
  created_at: string;
}

export interface PriceTagRequestSummary {
  id: string;
  doc_number: string;
  debtor_code: string | null;
  debtor_name: string;
  promotion_id: string | null;
  promotion_name: string | null;
  needed_by_date: string;
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
  attachments: PriceTagAttachment[];
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
  const usp = new URLSearchParams();
  if (params.query) usp.set('q', params.query);
  if (params.status) usp.set('status', params.status);

  const qs = usp.toString();
  const url = qs ? `${BASE}?${qs}` : BASE;
  const response = await apiFetch(url);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load price tag requests'));
  }

  const items: PriceTagRequestSummary[] = await response.json();

  // The backend returns a flat list without pagination. Apply client-side
  // sorting and pagination to match the component contract.
  if (params.sort) {
    const key = params.sort;
    const desc = params.dir === 'desc';
    items.sort((a, b) => {
      const av = (a as unknown as Record<string, unknown>)[key];
      const bv = (b as unknown as Record<string, unknown>)[key];
      const cmp = String(av ?? '').localeCompare(String(bv ?? ''));
      return desc ? -cmp : cmp;
    });
  }

  const total = items.length;
  const start = (params.page - 1) * params.limit;
  const page = items.slice(start, start + params.limit);

  return {
    data: page,
    pagination: { total, page: params.page, limit: params.limit },
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
 * Resolve display data for a request line.
 *
 * Prices resolve at render time (ADR 0008) - never stored in the tag sheet
 * doc. Marketing price override on the line wins over resolved price when set.
 */
export function resolveTagData(line: PriceTagRequestLine): ResolvedTagData {
  const listPrice = line.list_price;
  const sellPrice =
    line.marketing_price_override != null
      ? line.marketing_price_override
      : line.sell_price;

  return {
    product_image_url: null,
    code: line.code,
    name: line.name,
    dimensions: '',
    spec_lines: '',
    list_price: listPrice != null ? formatPrice(listPrice) : null,
    sell_price: sellPrice != null ? formatPrice(sellPrice) : null,
    show_promo_price: line.show_promo_price,
    included_accessories: line.included_accessories ?? '',
    alternatives: line.alternatives.map((a) => ({
      code: a.code,
      name: a.name,
      list_price: null,
    })),
    set_members: [],
  };
}

function formatPrice(amount: number): string {
  return `RM ${amount.toLocaleString('en-MY', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
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

/**
 * Resolve print payload for a request (all lines with prices).
 */
export function resolveAllLineData(
  request: PriceTagRequestDetail,
): Record<string, {
  line_id: string;
  code: string;
  name: string;
  dimensions: string;
  spec_lines: string;
  list_price: number | null;
  sell_price: number | null;
  show_promo_price: boolean;
  included_accessories: string;
  quantity: number;
}> {
  const result: Record<string, {
    line_id: string;
    code: string;
    name: string;
    dimensions: string;
    spec_lines: string;
    list_price: number | null;
    sell_price: number | null;
    show_promo_price: boolean;
    included_accessories: string;
    quantity: number;
  }> = {};

  for (const line of request.lines) {
    result[line.id] = {
      line_id: line.id,
      code: line.code,
      name: line.name,
      dimensions: '',
      spec_lines: '',
      list_price: line.list_price,
      sell_price: line.marketing_price_override ?? line.sell_price,
      show_promo_price: line.show_promo_price,
      included_accessories: line.included_accessories ?? '',
      quantity: line.quantity,
    };
  }

  return result;
}
