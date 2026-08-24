/**
 * Portal-side price tag request service.
 *
 * Calls `/api/v1/public/portal/submissions/price_tag_request` and
 * `/api/v1/public/portal/lookups` via `portalFetch`.
 */

import { portalFetch, unwrap } from './portal-client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type PriceTagLineType = 'product' | 'product_set';

export interface PriceTagRequestLine {
  id: string;
  line_type: PriceTagLineType;
  product_id: string | null;
  product_set_id: string | null;
  /** Human-readable name resolved from the product/set. */
  name: string;
  /** Human-readable code resolved from the product/set. */
  code: string;
  show_promo_price: boolean;
  quantity: number;
  alternatives: { product_id: string; name: string; code: string }[];
  included_accessories: string | null;
  sort_order: number;
  /** Derived class on the product - used for the set guard. */
  product_class?: string | null;
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
}

export interface PriceTagRequestDetail extends PriceTagRequestSummary {
  contact_id: string;
  lines: PriceTagRequestLine[];
  attachments: PriceTagAttachment[];
}

export interface PriceTagAttachment {
  id: string;
  filename: string;
  content_type: string | null;
  url: string | null;
  created_at: string;
}

export interface DebtorOption {
  code: string;
  name: string;
}

export interface PromotionOption {
  id: string;
  name: string;
}

export interface ProductOption {
  id: string;
  code: string;
  name: string;
  product_class: string | null;
}

export interface ProductSetOption {
  id: string;
  code: string;
  name: string;
}

export interface SetGuardResult {
  blocked: boolean;
  message: string | null;
  available_sets: { id: string; name: string }[];
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const BASE = '/api/v1/public/portal/submissions/price_tag_request';
const LOOKUPS = '/api/v1/public/portal/lookups';

// ---------------------------------------------------------------------------
// Lookups
// ---------------------------------------------------------------------------

export async function lookupDebtors(query?: string): Promise<DebtorOption[]> {
  const usp = new URLSearchParams();
  if (query) usp.set('q', query);
  const qs = usp.toString();
  const url = qs
    ? `${LOOKUPS}/debtors-for-agent?${qs}`
    : `${LOOKUPS}/debtors-for-agent`;
  const res = await portalFetch(url);
  const items = await unwrap<
    { customer_code: string | null; customer_name: string | null; debtor_code: string | null; debtor_name: string | null }[]
  >(res, 'Failed to load debtors');

  return items.map((d) => ({
    code: d.debtor_code ?? d.customer_code ?? '',
    name: d.debtor_name ?? d.customer_name ?? '',
  }));
}

// TODO: No portal promotions lookup endpoint exists yet. Keep client-side stub.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function lookupPromotions(query?: string): Promise<PromotionOption[]> {
  return [];
}

export async function lookupProducts(query?: string): Promise<ProductOption[]> {
  const usp = new URLSearchParams();
  if (query) usp.set('q', query);
  const qs = usp.toString();
  const url = qs
    ? `${LOOKUPS}/products?${qs}`
    : `${LOOKUPS}/products`;
  const res = await portalFetch(url);
  const items = await unwrap<
    { product_code: string; product_name: string | null; category_code: string | null; category_name: string | null }[]
  >(res, 'Failed to load products');

  return items.map((p) => ({
    // The portal products endpoint returns product_code, not an id.
    // Use product_code as the id since that is the identifier available.
    id: p.product_code,
    code: p.product_code,
    name: p.product_name ?? '',
    product_class: p.category_name ?? null,
  }));
}

// TODO: No portal product-sets lookup endpoint exists yet. Keep client-side stub.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function lookupProductSets(query?: string): Promise<ProductSetOption[]> {
  return [];
}

// ---------------------------------------------------------------------------
// Set guard
// ---------------------------------------------------------------------------

/**
 * Set guard check: client-side validation placeholder.
 * Server-side validation happens on submit.
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function checkSetGuard(productId: string): SetGuardResult {
  // Validation is enforced server-side on submit. The client-side check is
  // a no-op to avoid needing a dedicated endpoint.
  return { blocked: false, message: null, available_sets: [] };
}

// ---------------------------------------------------------------------------
// CRUD
// ---------------------------------------------------------------------------

export async function listRequests(): Promise<PriceTagRequestSummary[]> {
  const res = await portalFetch(BASE);
  const data = await unwrap<{ items: PriceTagRequestSummary[] }>(
    res,
    'Failed to load requests',
  );
  return data.items ?? [];
}

export async function getRequest(id: string): Promise<PriceTagRequestDetail | null> {
  const res = await portalFetch(
    `${BASE}/${encodeURIComponent(id)}`,
  );
  if (res.status === 404) return null;
  return unwrap<PriceTagRequestDetail>(res, 'Failed to load request');
}

export interface CreatePriceTagRequestInput {
  debtor_code: string;
  debtor_name: string;
  promotion_id: string | null;
  needed_by_date: string;
  notes: string | null;
  lines: Omit<PriceTagRequestLine, 'id' | 'name' | 'code' | 'sort_order'>[];
}

export async function createRequest(
  data: CreatePriceTagRequestInput,
): Promise<PriceTagRequestDetail> {
  const res = await portalFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return unwrap<PriceTagRequestDetail>(res, 'Failed to create request');
}

export async function updateRequest(
  id: string,
  data: Partial<CreatePriceTagRequestInput>,
): Promise<PriceTagRequestDetail> {
  const res = await portalFetch(
    `${BASE}/${encodeURIComponent(id)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    },
  );
  return unwrap<PriceTagRequestDetail>(res, 'Failed to update request');
}

export async function submitRequest(id: string): Promise<{ status: string }> {
  const res = await portalFetch(
    `${BASE}/${encodeURIComponent(id)}/submit`,
    { method: 'POST' },
  );
  return unwrap<{ status: string }>(res, 'Failed to submit request');
}

export async function approveRequest(id: string): Promise<{ status: string }> {
  const res = await portalFetch(
    `${BASE}/${encodeURIComponent(id)}/approve`,
    { method: 'POST' },
  );
  return unwrap<{ status: string }>(res, 'Failed to approve request');
}

export async function requestChanges(
  id: string,
  note: string,
): Promise<{ status: string }> {
  const res = await portalFetch(
    `${BASE}/${encodeURIComponent(id)}/request-changes`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note }),
    },
  );
  return unwrap<{ status: string }>(res, 'Failed to request changes');
}
