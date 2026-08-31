/**
 * Portal-side price tag request service.
 *
 * Calls `/api/v1/public/portal/submissions/price_tag_request` and
 * `/api/v1/public/portal/lookups` via `portalFetch`.
 */

import { extractApiError } from '@/lib/api-client';
import {
  portalFetch,
  unwrap,
  type PortalSubmissionSummary,
} from './portal-client';

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
  /** Null on a draft: Save Draft validates nothing (D48a). */
  debtor_name: string | null;
  promotion_id: string | null;
  promotion_name: string | null;
  /** Null on a draft, for the same reason as `debtor_name`. */
  needed_by_date: string | null;
  notes: string | null;
  status: string;
  line_count: number;
  created_at: string;
  /** Set while the request is a draft the salesperson has not submitted. */
  portal_draft_at?: string | null;
}

export interface PriceTagRequestDetail extends PriceTagRequestSummary {
  contact_id: string;
  lines: PriceTagRequestLine[];
  attachments: PriceTagAttachment[];
  /** Set while the request is a draft. This, not the status, is what says so:
   *  a draft's status is `new`, the same status a submitted request keeps until
   *  marketing claims it. */
  portal_draft_at?: string | null;
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

/**
 * One row of the lines table's single Item picker (D47): a set OR a product, in
 * the same list, because a dealer does not know which of the two a thing is.
 *
 * `id` is the real `products.id` / `product_sets.id`, which is what a line's
 * foreign key stores. The portal's generic product lookup answers with a code and
 * no id at all, so a product line built from it could never be saved.
 */
export interface TagItemOption {
  kind: PriceTagLineType;
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

/**
 * Sets and products in one list, for the lines table's single Item dropdown.
 *
 * The alternatives picker reads the same call and keeps the products: one endpoint
 * for one question ("what can go on a tag?") beats two round trips per keystroke,
 * and the handful of sets it also returns costs nothing.
 */
export async function lookupTagItems(query?: string): Promise<TagItemOption[]> {
  const usp = new URLSearchParams();
  if (query && query.trim()) usp.set('q', query.trim());
  const qs = usp.toString();
  const url = qs
    ? `${LOOKUPS}/price-tag-items?${qs}`
    : `${LOOKUPS}/price-tag-items`;
  const res = await portalFetch(url);
  return unwrap<TagItemOption[]>(res, 'Failed to load products and sets');
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
// Refusals that name a field
// ---------------------------------------------------------------------------

/**
 * A refusal the form can put where the problem is (D48b).
 *
 * The server answers `{message, detail, code}` and `detail` on these routes is a
 * comma-separated list of field keys: `debtor_name`, `needed_by_date`, `lines`,
 * `line:<index>`. `unwrap` keeps only the message, which is why a set guard
 * refusal used to arrive as a toast with no way back to the row it was about.
 */
export class PriceTagRequestError extends Error {
  readonly code: string | null;
  readonly fields: string[];

  constructor(message: string, code: string | null, fields: string[]) {
    super(message);
    this.name = 'PriceTagRequestError';
    this.code = code;
    this.fields = fields;
  }
}

async function unwrapNamingFields<T>(res: Response, fallback: string): Promise<T> {
  if (res.ok) return (await res.json()) as T;
  // The clone is what lets `extractApiError` own the message (one implementation
  // of that, per PRINCIPLES) while this still reads the code and the field list
  // beside it. A body can only be consumed once.
  const spare = res.clone();
  const message = await extractApiError(res, fallback);
  let body: { code?: unknown; detail?: unknown } | null = null;
  try {
    body = (await spare.json()) as { code?: unknown; detail?: unknown };
  } catch {
    body = null;
  }
  const code = typeof body?.code === 'string' ? body.code : null;
  const fields =
    typeof body?.detail === 'string' && body.detail
      ? body.detail.split(',').map((f) => f.trim()).filter(Boolean)
      : [];
  throw new PriceTagRequestError(message, code, fields);
}

// ---------------------------------------------------------------------------
// CRUD
// ---------------------------------------------------------------------------

export async function listRequests(
  q?: string,
): Promise<PriceTagRequestSummary[]> {
  const usp = new URLSearchParams();
  if (q && q.trim()) usp.set('q', q.trim());
  const qs = usp.toString();
  const res = await portalFetch(qs ? `${BASE}?${qs}` : BASE);
  const data = await unwrap<{ items: PriceTagRequestSummary[] }>(
    res,
    'Failed to load requests',
  );
  return data.items ?? [];
}

/**
 * The same list in the shape the portal landing's cards read (D45).
 *
 * The price tag endpoint answers its own row type rather than the legacy
 * `PortalSubmissionSummary`, and adapting it HERE is what lets the landing stay
 * ignorant of the difference without any legacy endpoint changing. `doc_number`
 * is the card's primary line, the dealer is its customer line, and a request
 * still carrying `portal_draft_at` is a draft, which is the only thing that
 * tells a saved-but-unsent request from a submitted one.
 */
export async function listRequestsAsSummaries(
  q?: string,
): Promise<PortalSubmissionSummary[]> {
  const rows = await listRequests(q);
  return rows.map((r) => {
    const isDraft = Boolean(r.portal_draft_at);
    return {
      id: r.id,
      kind: 'price_tag_request' as const,
      // A draft may have no dealer yet, and a card with a blank first line reads
      // as a broken row rather than an unfinished one.
      title: r.debtor_name || r.doc_number,
      document_number: r.doc_number,
      reference: null,
      status: r.status,
      is_editable: isDraft,
      is_draft: isDraft,
      created_at: r.created_at,
      customer_name: r.debtor_name,
      needed_by_date: r.needed_by_date,
    };
  });
}

export async function getRequest(id: string): Promise<PriceTagRequestDetail | null> {
  const res = await portalFetch(
    `${BASE}/${encodeURIComponent(id)}`,
  );
  if (res.status === 404) return null;
  return unwrap<PriceTagRequestDetail>(res, 'Failed to load request');
}

/**
 * What Save Draft posts, which is whatever the salesperson has filled in so far
 * (D48a). Everything is nullable because the request row is: completeness is
 * checked on submit, where the server can name what is missing.
 */
export interface CreatePriceTagRequestInput {
  debtor_code: string | null;
  debtor_name: string | null;
  promotion_id: string | null;
  needed_by_date: string | null;
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
  return unwrapNamingFields<PriceTagRequestDetail>(res, 'Failed to create request');
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
  return unwrapNamingFields<PriceTagRequestDetail>(res, 'Failed to update request');
}

export async function submitRequest(id: string): Promise<{ status: string }> {
  const res = await portalFetch(
    `${BASE}/${encodeURIComponent(id)}/submit`,
    { method: 'POST' },
  );
  return unwrapNamingFields<{ status: string }>(res, 'Failed to submit request');
}

/** Hard-delete a draft. The server refuses once it has been submitted. */
export async function deleteRequest(id: string): Promise<void> {
  const res = await portalFetch(`${BASE}/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
  if (res.ok) return;
  throw new Error(await extractApiError(res, 'Failed to delete draft'));
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
