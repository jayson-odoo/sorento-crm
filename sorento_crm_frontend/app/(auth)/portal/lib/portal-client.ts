/**
 * Portal API client - token-scoped, no NextAuth session.
 *
 * The token is stored in localStorage (device trust - survives tab close;
 * the BE gives verified tokens a sliding 30-day TTL) and sent as
 * `X-Portal-Token` on every request. On 401 the caller is responsible for
 * redirecting to the verify page.
 *
 * Impersonation sessions are the exception: their token lives in
 * sessionStorage only, so an admin "view as contact" never leaves a 30-day
 * credential on the admin's machine. sessionStorage wins on read so an
 * active impersonation takes precedence in its tab.
 */
import { extractApiError } from '@/lib/api-client';

const TOKEN_KEY = 'sorento.portalToken';

export type PortalSubmissionKind =
  | 'complaint'
  | 'stock_inquiry'
  | 'purchase_request'
  | 'sponsorship_form';

/** Canonical kind list - single source for route guards, tab lists, labels. */
export const SUBMISSION_KINDS: readonly PortalSubmissionKind[] = [
  'complaint',
  'stock_inquiry',
  'purchase_request',
  'sponsorship_form',
] as const;

export function isSubmissionKind(
  value: string | null | undefined,
): value is PortalSubmissionKind {
  return (SUBMISSION_KINDS as readonly string[]).includes(value ?? '');
}

export interface PortalImpersonationInfo {
  session_id: string;
  admin_user_id: string;
  admin_name: string | null;
  admin_email: string | null;
  started_at: string;
}

export interface PortalContact {
  contact_id: string;
  space_id: string;
  name: string | null;
  phone_number: string | null;
  expires_at: string;
  /** Stable slug behind the bookmarkable URL /portal/c/{slug}. */
  portal_slug?: string | null;
  /** Business WhatsApp number (digits) for the wa.me escape hatch. */
  whatsapp_number?: string | null;
  impersonation?: PortalImpersonationInfo | null;
  /** Maps BROWSER key. Public by design, restricted by HTTP referrer in Google Cloud.
   *  Null means the tenant configured none: typed fields, no map, still submittable. */
  google_maps_api_key?: string | null;
}

export interface PortalSubmissionSummary {
  id: string;
  kind: PortalSubmissionKind;
  title: string;
  document_number?: string | null;
  reference: string | null;
  status: string;
  approval_status?: string | null;
  rejection_reason?: string | null;
  is_editable: boolean;
  is_draft: boolean;
  created_at: string | null;
  // Optional kind-specific summary fields surfaced for the mobile card layout.
  product_code?: string | null;
  project_title?: string | null;
  project_name?: string | null;
  project_customer?: string | null;
  customer_name?: string | null;
  delivery_order_number?: string | null;
  item_description?: string | null;
  sponsor_subject?: string | null;
  purpose?: string | null;
}

export type PortalAttachmentUploaderKind = 'user' | 'contact' | 'system' | null;
export type PortalAttachmentUploaderRole = 'contact' | 'staff' | 'unknown';

export interface PortalAttachment {
  link_id: string;
  attachment_id: string;
  filename: string | null;
  size: number | null;
  url: string | null;
  content_type?: string | null;
  uploaded_at?: string | null;
  /** 'user' = uploaded by CRM staff, 'contact' = uploaded by this contact,
   *  'system' = worker-created. Absent/null on legacy rows. */
  uploader_kind?: PortalAttachmentUploaderKind;
  uploaded_by_name?: string | null;
  uploaded_by_role?: PortalAttachmentUploaderRole;
  /** false for staff ('user') uploads - the contact cannot unlink those. */
  can_unlink?: boolean;
}

export interface PortalSubmissionDetail extends PortalSubmissionSummary {
  attachments?: PortalAttachment[];
  // Free-form fields per type, populated by the backend serializer.
  [key: string]: unknown;
}

export class PortalUnauthorizedError extends Error {
  constructor(message = 'Portal session expired.') {
    super(message);
    this.name = 'PortalUnauthorizedError';
  }
}

/**
 * The submission exists but belongs to a different contact than the current
 * session (403 OWNER_MISMATCH). The current token stays valid - the caller
 * should route to the owner's confirm-identity card (the deep-link slug), not
 * clear the session.
 */
export class PortalOwnerMismatchError extends Error {
  constructor(message = 'This submission belongs to another contact.') {
    super(message);
    this.name = 'PortalOwnerMismatchError';
  }
}

export function readPortalToken(): string | null {
  if (typeof window === 'undefined') return null;
  // Impersonation (sessionStorage) wins over device trust (localStorage).
  return (
    window.sessionStorage.getItem(TOKEN_KEY) ?? window.localStorage.getItem(TOKEN_KEY)
  );
}

export function writePortalToken(
  token: string,
  opts: { impersonation?: boolean } = {},
): void {
  if (typeof window === 'undefined') return;
  if (opts.impersonation) {
    window.sessionStorage.setItem(TOKEN_KEY, token);
  } else {
    window.localStorage.setItem(TOKEN_KEY, token);
    // Drop any stale impersonation token so the new identity wins.
    window.sessionStorage.removeItem(TOKEN_KEY);
  }
}

export function clearPortalToken(): void {
  if (typeof window === 'undefined') return;
  window.sessionStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(TOKEN_KEY);
}

/**
 * Clear ONLY the session-scoped (impersonation) token. Used on impersonation
 * exit so an admin's own device-trust token in localStorage survives.
 */
export function clearImpersonationToken(): void {
  if (typeof window === 'undefined') return;
  window.sessionStorage.removeItem(TOKEN_KEY);
}

/** True when the active token is an impersonation (sessionStorage) token. */
export function isImpersonationToken(): boolean {
  if (typeof window === 'undefined') return false;
  return window.sessionStorage.getItem(TOKEN_KEY) != null;
}

/**
 * Migrate the active token into sessionStorage. Safety net for impersonation
 * links that lack the `?impersonation=1` marker: once /me reveals an
 * impersonation session, the token must not persist on the admin's machine.
 */
export function demoteTokenToSession(): void {
  if (typeof window === 'undefined') return;
  const t = window.localStorage.getItem(TOKEN_KEY);
  if (t) {
    window.sessionStorage.setItem(TOKEN_KEY, t);
    window.localStorage.removeItem(TOKEN_KEY);
  }
}

/**
 * Resolve the backend base URL.
 *
 * - In production (or when NEXT_PUBLIC_API_URL is set), this is the absolute
 *   API host.
 * - In development with no NEXT_PUBLIC_API_URL, the empty string keeps URLs
 *   relative so the Next.js rewrite proxies `/api/v1/*` to the FastAPI server.
 *
 * Multipart uploads use {@link absoluteApiUrl} to bypass the rewrite, since
 * Next.js dev rewrites can mangle streaming `multipart/form-data` bodies.
 */
function apiBase(): string {
  if (typeof process !== 'undefined') {
    const env = process.env?.NEXT_PUBLIC_API_URL;
    if (env) return env.replace(/\/$/, '');
  }
  return '';
}

function absoluteApiUrl(path: string): string {
  const base = apiBase();
  if (base) return `${base}${path.startsWith('/') ? path : `/${path}`}`;
  // Dev fallback: hit FastAPI directly to bypass the Next.js rewrite, which
  // can corrupt multipart bodies in some Next 15 builds.
  if (typeof window !== 'undefined') {
    const port = window.location.port;
    if (port === '3000' || port === '3001') {
      return `${window.location.protocol}//${window.location.hostname}:8000${path}`;
    }
  }
  return path;
}

async function portalFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const token = readPortalToken();
  const headers = new Headers(init.headers || {});
  if (token) headers.set('X-Portal-Token', token);
  const res = await fetch(input, { ...init, headers });
  if (res.status === 401) {
    clearPortalToken();
    throw new PortalUnauthorizedError();
  }
  return res;
}

async function portalMultipartFetch(
  path: string,
  form: FormData,
): Promise<Response> {
  const token = readPortalToken();
  const url = absoluteApiUrl(path);
  // IMPORTANT: do NOT pass a Content-Type header. fetch must auto-set
  // 'multipart/form-data; boundary=...' when body is FormData. Passing a
  // Headers object with only X-Portal-Token is fine; fetch fills in CT itself.
  const init: RequestInit = {
    method: 'POST',
    body: form,
    headers: token ? { 'X-Portal-Token': token } : undefined,
  };
  // Cross-origin in dev: we hit :8000 from :3000. CORS must allow.
  if (url.startsWith('http')) {
    init.mode = 'cors';
    init.credentials = 'omit';
  }
  const res = await fetch(url, init);
  if (res.status === 401) {
    clearPortalToken();
    throw new PortalUnauthorizedError();
  }
  return res;
}

async function unwrap<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) {
    const message = await extractApiError(res, fallback);
    throw new Error(message);
  }
  return (await res.json()) as T;
}

export async function fetchMe(): Promise<PortalContact> {
  const res = await portalFetch('/api/v1/public/portal/me');
  return unwrap<PortalContact>(res, 'Failed to load profile.');
}

/**
 * fetchMe with the fresh-token grace retry: a token written by /verify-otp in
 * the last 30s can transiently 401 (commit-visibility race between the verify
 * commit and a fast follow-up /me). portalFetch clears the token on 401, so
 * restore it and retry once before treating the session as dead.
 */
export async function fetchMeWithGrace(): Promise<PortalContact> {
  const existing = readPortalToken();
  const wasImpersonation = isImpersonationToken();
  const writtenAt =
    typeof window !== 'undefined'
      ? Number(window.sessionStorage.getItem('sorento.portalTokenWrittenAt') || '0')
      : 0;
  const tokenIsFresh = writtenAt > 0 && Date.now() - writtenAt < 30_000;
  try {
    return await fetchMe();
  } catch (firstErr) {
    if (firstErr instanceof PortalUnauthorizedError && tokenIsFresh && existing) {
      // Restore to the SAME store it came from - an impersonation token must
      // not be promoted into localStorage by the retry.
      writePortalToken(existing, { impersonation: wasImpersonation });
      await new Promise((r) => setTimeout(r, 500));
      return fetchMe();
    }
    throw firstErr;
  }
}

export async function stopPortalImpersonation(): Promise<void> {
  const res = await portalFetch('/api/v1/public/portal/impersonation/stop', {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error(await extractApiError(res, 'Failed to exit impersonation.'));
  }
}

export async function fetchSubmissions(
  kind: PortalSubmissionKind,
  q?: string,
): Promise<PortalSubmissionSummary[]> {
  const usp = new URLSearchParams({ type: kind });
  if (q && q.trim()) usp.set('q', q.trim());
  const res = await portalFetch(`/api/v1/public/portal/submissions?${usp.toString()}`);
  const data = await unwrap<{ items: PortalSubmissionSummary[] }>(res, 'Failed to load submissions.');
  return data.items ?? [];
}

export async function fetchSubmission(
  kind: PortalSubmissionKind,
  id: string
): Promise<PortalSubmissionDetail> {
  const res = await portalFetch(`/api/v1/public/portal/submissions/${kind}/${encodeURIComponent(id)}`);
  // 403 OWNER_MISMATCH: session is valid but the form belongs to another
  // contact - surface as a typed error so the caller offers owner login.
  if (res.status === 403) {
    // The global handler flattens AppException to {message, detail, code}.
    const body = await res.clone().json().catch(() => ({}));
    const code = body?.code ?? body?.detail?.code;
    if (code === 'OWNER_MISMATCH') {
      throw new PortalOwnerMismatchError(body?.message ?? body?.detail?.message);
    }
  }
  return unwrap<PortalSubmissionDetail>(res, 'Failed to load submission.');
}

export async function saveDraft(
  kind: PortalSubmissionKind,
  fields: Record<string, unknown>,
  products?: Record<string, unknown>[],
  id?: string
): Promise<PortalSubmissionDetail> {
  const url = id
    ? `/api/v1/public/portal/submissions/${kind}/${encodeURIComponent(id)}`
    : `/api/v1/public/portal/submissions/${kind}`;
  const res = await portalFetch(url, {
    method: id ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fields, products }),
  });
  return unwrap<PortalSubmissionDetail>(res, 'Failed to save draft.');
}

export async function submitDraft(
  kind: PortalSubmissionKind,
  id: string,
  fields?: Record<string, unknown>,
  products?: Record<string, unknown>[]
): Promise<PortalSubmissionDetail> {
  const body = fields || products ? JSON.stringify({ fields: fields || {}, products }) : undefined;
  const res = await portalFetch(`/api/v1/public/portal/submissions/${kind}/${encodeURIComponent(id)}/submit`, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body,
  });
  return unwrap<PortalSubmissionDetail>(res, 'Failed to submit.');
}

export async function deleteDraftSubmission(
  kind: PortalSubmissionKind,
  id: string,
): Promise<void> {
  const res = await portalFetch(
    `/api/v1/public/portal/submissions/${kind}/${encodeURIComponent(id)}`,
    { method: 'DELETE' },
  );
  if (!res.ok && res.status !== 204) {
    const message = await extractApiError(res, 'Failed to delete draft.');
    throw new Error(message);
  }
}

export async function uploadAttachment(
  kind: PortalSubmissionKind,
  submissionId: string,
  file: File
): Promise<PortalAttachment> {
  const form = new FormData();
  form.set('kind', kind);
  form.set('submission_id', submissionId);
  form.set('file', file, file.name);
  const res = await portalMultipartFetch('/api/v1/public/portal/attachments', form);
  return unwrap<PortalAttachment>(res, 'Upload failed.');
}

export async function deleteAttachment(linkId: string): Promise<void> {
  const res = await portalFetch(`/api/v1/public/portal/attachments/${encodeURIComponent(linkId)}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const message = await extractApiError(res, 'Failed to remove attachment.');
    throw new Error(message);
  }
}

export async function requestOtp(contactId: string, spaceId: string): Promise<{ sent_to: string | null; expires_at: string }> {
  const res = await fetch('/api/v1/public/portal/request-otp', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ contact_id: contactId, space_id: spaceId }),
  });
  return unwrap(res, 'Failed to send verification code.');
}

export async function verifyOtp(
  contactId: string,
  spaceId: string,
  code: string
): Promise<{ token: string; expires_at: string }> {
  const res = await fetch('/api/v1/public/portal/verify-otp', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ contact_id: contactId, space_id: spaceId, code }),
  });
  return unwrap(res, 'Failed to verify code.');
}

export interface PortalTokenInfo {
  contact_id: string;
  space_id: string;
  expires_at: string;
  expired: boolean;
  revoked: boolean;
  portal_slug?: string | null;
  name?: string | null;
  masked_phone?: string | null;
  whatsapp_number?: string | null;
}

// ---------------------------------------------------------------------------
// Bookmarkable slug links (see documentation/plans/PLAN-portal-bookmarkable-links.md)
// ---------------------------------------------------------------------------

export interface PortalSlugInfo {
  contact_id: string;
  space_id: string;
  name: string | null;
  masked_phone: string | null;
  whatsapp_number: string | null;
}

/** GET /api/v1/public/portal/slug-info/{slug} - null mirrors the 404. */
export async function fetchSlugInfo(slug: string): Promise<PortalSlugInfo | null> {
  const res = await fetch(
    `/api/v1/public/portal/slug-info/${encodeURIComponent(slug)}`,
    { method: 'GET' },
  );
  if (res.status === 404) return null;
  return unwrap<PortalSlugInfo>(res, 'Could not look up portal link.');
}

/**
 * POST /api/v1/public/portal/logout - revokes the active token server-side
 * (clearing client storage alone would leave a copied token valid).
 */
export async function portalLogout(): Promise<void> {
  const token = readPortalToken();
  if (!token) return;
  await fetch('/api/v1/public/portal/logout', {
    method: 'POST',
    headers: { 'X-Portal-Token': token },
  });
}

export async function fetchTokenInfo(token: string): Promise<PortalTokenInfo> {
  const res = await fetch(
    `/api/v1/public/portal/token-info?token=${encodeURIComponent(token)}`,
    { method: 'GET' },
  );
  return unwrap(res, 'Could not look up portal token.');
}

export const SUBMISSION_LABELS: Record<PortalSubmissionKind, string> = {
  complaint: 'Complaint',
  stock_inquiry: 'Stock Inquiry',
  purchase_request: 'Purchase Request',
  sponsorship_form: 'Sponsorship Form',
};

// Friendly labels for backend status / approval_status values surfaced in the
// portal. Falls back to the raw value when not in this map.
export const SUBMISSION_STATUS_LABELS: Record<string, string> = {
  draft: 'Draft',
  new: 'New',
  pending: 'Pending',
  pending_approval: 'Pending approval',
  pending_project_sales: 'Pending project sales',
  pending_purchasing: 'Pending purchasing',
  approved: 'Approved',
  rejected: 'Rejected',
  responded: 'Responded',
  submitted: 'Submitted',
  processed_by_cs: 'Processed by CS',
  closed: 'Closed',
  completed: 'Completed',
  updated: 'Updated',
};

export function statusLabel(status: string | null | undefined): string {
  const s = (status ?? '').trim();
  if (!s) return '';
  return SUBMISSION_STATUS_LABELS[s] ?? s;
}

// ---------------------------------------------------------------------------
// Lookup helpers for portal forms (searchable comboboxes / select sets)
// ---------------------------------------------------------------------------

export interface ProductLookupItem {
  product_code: string;
  product_name: string | null;
  category_id: string | null;
  category_code?: string | null;
  category_name?: string | null;
}

export interface DebtorLookupItem {
  debtor_name: string;
}

export interface DOProductLine {
  product_code: string;
  product_name?: string | null;
  quantity?: number | null;
}

export interface DOLookupItem {
  order_number: string;
  debtor_name: string | null;
  customer_name: string | null;
  products: string[];
  product_lines?: DOProductLine[];
  order_date?: string | null;
}

export interface DOLookupFilters {
  start_date?: string;
  end_date?: string;
  product_code?: string;
  debtor_name?: string;
}

export interface LookupSetOption {
  value: string;
  label: string;
}

export async function lookupProducts(q: string, limit = 20): Promise<ProductLookupItem[]> {
  const url = `/api/v1/public/portal/lookups/products?q=${encodeURIComponent(q)}&limit=${limit}`;
  const res = await portalFetch(url);
  return unwrap<ProductLookupItem[]>(res, 'Failed to load products.');
}

export async function lookupDebtors(q: string, limit = 20): Promise<DebtorLookupItem[]> {
  const url = `/api/v1/public/portal/lookups/debtors?q=${encodeURIComponent(q)}&limit=${limit}`;
  const res = await portalFetch(url);
  return unwrap<DebtorLookupItem[]>(res, 'Failed to load debtors.');
}

export async function lookupDeliveryOrders(
  q: string,
  limit = 20,
  filters: DOLookupFilters = {},
): Promise<DOLookupItem[]> {
  const params = new URLSearchParams({ q, limit: String(limit) });
  if (filters.start_date) params.set('start_date', filters.start_date);
  if (filters.end_date) params.set('end_date', filters.end_date);
  if (filters.product_code) params.set('product_code', filters.product_code);
  if (filters.debtor_name) params.set('debtor_name', filters.debtor_name);
  const url = `/api/v1/public/portal/lookups/delivery-orders?${params.toString()}`;
  const res = await portalFetch(url);
  return unwrap<DOLookupItem[]>(res, 'Failed to load delivery orders.');
}

export interface LookupSetResult {
  options: LookupSetOption[];
  defaultValue: string | null;
}

// ---------------------------------------------------------------------------
// Requestor picker ("Requested by" / "Salesperson") - segment-gated contacts
// ---------------------------------------------------------------------------

export interface RequestorOption {
  id: string;
  name: string;
}

export interface RequestorOptionsResult {
  items: RequestorOption[];
  hasMore: boolean;
}

/** GET /api/v1/public/portal/requestor-options?q= - names only, segment-gated
 *  (plus the submitting contact, always included server-side). */
export async function fetchRequestorOptions(q?: string): Promise<RequestorOptionsResult> {
  const usp = new URLSearchParams();
  if (q && q.trim()) usp.set('q', q.trim());
  const qs = usp.toString();
  const res = await portalFetch(`/api/v1/public/portal/requestor-options${qs ? `?${qs}` : ''}`);
  const data = await unwrap<{ items?: RequestorOption[]; has_more?: boolean }>(
    res,
    'Failed to load requestor options.',
  );
  return { items: data.items ?? [], hasMore: Boolean(data.has_more) };
}

// ---------------------------------------------------------------------------
// Record navigation (previous/next submission of the same kind)
// ---------------------------------------------------------------------------

export interface PortalSubmissionNeighbours {
  prev_id: string | null;
  next_id: string | null;
  position: number;
  total: number;
}

/** GET .../submissions/{kind}/{id}/neighbours - token-scoped to the contact's
 *  own submissions of the same kind, newest first. */
export async function fetchSubmissionNeighbours(
  kind: PortalSubmissionKind,
  id: string,
): Promise<PortalSubmissionNeighbours> {
  const res = await portalFetch(
    `/api/v1/public/portal/submissions/${kind}/${encodeURIComponent(id)}/neighbours`,
  );
  return unwrap<PortalSubmissionNeighbours>(res, 'Failed to load navigation.');
}

const _lookupSetCache: Record<string, LookupSetResult> = {};
export async function lookupSet(setKey: string): Promise<LookupSetResult> {
  if (_lookupSetCache[setKey]) return _lookupSetCache[setKey];
  const url = `/api/v1/public/portal/lookups/sets/${encodeURIComponent(setKey)}`;
  const res = await portalFetch(url);
  const data = await unwrap<{ options: LookupSetOption[]; default_value: string | null }>(
    res,
    'Failed to load lookup options.',
  );
  const result: LookupSetResult = {
    options: data?.options ?? [],
    defaultValue: data?.default_value ?? null,
  };
  _lookupSetCache[setKey] = result;
  return result;
}

// ---------------------------------------------------------------------------
// AI Extract - generic form prefill from attachments (images + PDFs)
// ---------------------------------------------------------------------------

export interface AIExtractFieldMeta {
  raw?: unknown;
  canonical?: unknown;
  source?: string | null;
}

export interface AIExtractedProductLine {
  product_code?: string | null;
  product_name?: string | null;
  quantity?: number | null;
  unit_price?: number | null;
  total?: number | null;
  notes?: string | null;
}

export interface AIExtractTokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface AIExtractResult {
  values: Record<string, unknown>;
  products: AIExtractedProductLine[];
  per_field: Record<string, AIExtractFieldMeta>;
  usage: AIExtractTokenUsage;
  model?: string | null;
  provider?: string | null;
  /** The uploaded files, stored by the endpoint before extraction ran. Sent back on
   *  submit so the evidence lands on the record - the extractor's opinion of a file is
   *  never what decides whether it is kept. */
  attachment_ids?: string[];
}

export const AI_EXTRACT_FORM_KEYS: Record<PortalSubmissionKind, string> = {
  complaint: 'portal.complaint',
  stock_inquiry: 'portal.stock_inquiry',
  purchase_request: 'portal.purchase_request',
  sponsorship_form: 'portal.sponsorship_form',
};

/**
 * The consumer track's own form key, deliberately NOT `portal.complaint`.
 *
 * `portal.complaint` reads a Sorento delivery order: it asks for a DO number and for the
 * BUYER being billed. A consumer's attachment is the DEALER's own invoice, where the
 * company on the letterhead is the SELLER and the document number matches nothing in
 * `orders` - six for six in the S3-pre spike (AC-C12). Not a `PortalSubmissionKind`,
 * because a consumer lodgement is not one of the four portal form types.
 */
export const CONSUMER_LODGE_FORM_KEY = 'portal.consumer_lodge';

export async function aiExtractFromFiles(
  formKey: string,
  files: File[],
): Promise<AIExtractResult> {
  if (!files.length) throw new Error('Drop at least one file before extracting.');
  const form = new FormData();
  form.set('form_key', formKey);
  for (const file of files) {
    form.append('files', file, file.name);
  }
  const res = await portalMultipartFetch('/api/v1/public/portal/ai-extract', form);
  return unwrap<AIExtractResult>(res, 'AI extract failed.');
}

// --------------------------------------------------------------------------- //
// Consumer intake (S3). The lodge journey, off mocks.                          //
// --------------------------------------------------------------------------- //

/**
 * `dealer.state` is the load-bearing field and it is a STATE, never a confidence
 * float. The S3-pre spike measured a bimodal distribution - 26 of 38 receipts at
 * exactly 1.00, nothing at all between 0.70 and 0.99 - so there is no gradient for a
 * frontend to threshold, and three receipts in the middle band named a real but WRONG
 * dealer. A float would invite this file to invent a cutoff and eventually pre-fill one
 * of those.
 *
 * From the consumer's side `candidate` and `unmatched` look identical: they see only
 * their own typed shop name. The difference is what CS receives.
 */
export type LodgeDealerState = 'resolved' | 'candidate' | 'unmatched';

/** How a typed model code resolved. `ambiguous` is normal traffic, not an error:
 *  `SRTWC8152` covers three real variants, so the Kind answers instead (AC-C17). */
export type LodgeProductState = 'exact' | 'ambiguous' | 'candidates' | 'unmatched';

export interface LodgeKindTile {
  kind_code: string;
  label: string;
  /** Null for every Kind today. Sorento accepted text-only tiles; the field exists so
   *  adding artwork later needs no contract change. */
  icon: string | null;
  sort_order: number;
}

export interface LodgeProductCandidate {
  product_id: string;
  product_code: string;
  product_name: string;
}

export interface LodgeResolvedLine {
  index: number;
  claimed_text: string | null;
  model_code_raw: string | null;
  state: LodgeProductState;
  /** Null whenever the code was ambiguous - the variant is CS's to choose. */
  product_id: string | null;
  product_code: string | null;
  product_name: string | null;
  candidates: LodgeProductCandidate[];
  /** True when the tiled chooser has to answer for this line. */
  needs_kind: boolean;
  kind_code: string | null;
}

export interface LodgeResolveResult {
  dealer: {
    state: LodgeDealerState;
    printed_name: string | null;
    customer_id: string | null;
    customer_name: string | null;
    /** For CS only. Never rendered to a consumer. */
    suggestion_name: string | null;
  };
  lines: LodgeResolvedLine[];
}

export interface LodgeLineInput {
  claimed_text?: string | null;
  model_code_raw?: string | null;
  kind_code?: string | null;
  quantity?: number | null;
  fault_description?: string | null;
}

export interface LodgeSubmitInput extends Record<string, unknown> {
  phone: string;
  full_name?: string | null;
  shop_name?: string | null;
  purchase_date?: string | null;
  dealer_document_number?: string | null;
  site_address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  defect_description?: string | null;
  proof_attachment_id?: string | null;
  /** Everything the consumer uploaded, linked to the complaint on submit. Separate from
   *  `proof_attachment_id`, which names the ONE file the purchase record treats as proof:
   *  a photo of a cracked basin is evidence, but calling it proof of purchase would be a
   *  lie the warranty engine reads. */
  attachment_ids?: string[];
  lines: LodgeLineInput[];
}

export interface LodgeWarrantyVerdict {
  complaint_product_line_id: string;
  claimed_text: string | null;
  part_name: string | null;
  verdict: string | null;
  expires_on: string | null;
}

export interface LodgeSubmitResult {
  complaint_id: string;
  complaint_number: string | null;
  purchase_id: string | null;
  dealer_state: LodgeDealerState;
  dealer_name: string | null;
  /** One entry per part per line. EMPTY is a normal answer: no purchase date means no
   *  verdict, and saying so beats inventing one. */
  warranty: LodgeWarrantyVerdict[];
}

export async function fetchLodgeKinds(): Promise<LodgeKindTile[]> {
  const res = await portalFetch('/api/v1/public/portal/lodge/kinds');
  const body = await unwrap<{ kinds: LodgeKindTile[] }>(res, 'Failed to load the product list.');
  return body.kinds;
}

/**
 * "Did I get this right?" - re-runnable and side-effect free.
 *
 * Called every time the consumer edits the shop name, because extraction pre-fills an
 * EDITABLE form rather than a read-only confirmation. That is what turns a bad
 * extraction into one edit by the consumer instead of a cleanup by CS.
 */
export async function resolveLodge(payload: {
  shop_name?: string | null;
  lines: LodgeLineInput[];
}): Promise<LodgeResolveResult> {
  const res = await portalFetch('/api/v1/public/portal/lodge/resolve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return unwrap<LodgeResolveResult>(res, 'Could not check those details.');
}

/** Submit. Nothing blocks it but consent (AC-C14). */
export async function submitLodge(payload: LodgeSubmitInput): Promise<LodgeSubmitResult> {
  const res = await portalFetch('/api/v1/public/portal/lodge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return unwrap<LodgeSubmitResult>(res, 'Could not submit your report.');
}

/**
 * One sentence a homeowner can act on, from a list of per-part verdicts.
 *
 * The engine answers per PART - a water closet has a ceramic body, a seat cover and a
 * flush mechanism, each with its own term - and a consumer reading five rows learns
 * less than one reading a sentence. The parts stay available for anyone who wants them;
 * this is the headline, and it deliberately never says "not covered" when any part is,
 * because the visit is what matters to them.
 */
export function summariseWarranty(verdicts: LodgeWarrantyVerdict[]): {
  state: 'covered' | 'expired' | 'needs_review';
  summary: string;
} {
  if (!verdicts.length) {
    return {
      state: 'needs_review',
      summary: 'We could not work out your warranty automatically. Our team will check it for you.',
    };
  }
  const values = verdicts.map((v) => (v.verdict || '').toLowerCase());
  if (values.some((v) => v === 'covered')) {
    const dated = verdicts.find((v) => (v.verdict || '').toLowerCase() === 'covered' && v.expires_on);
    return {
      state: 'covered',
      summary: dated?.expires_on
        ? `Covered by warranty until ${dated.expires_on}.`
        : 'Covered by warranty.',
    };
  }
  if (values.every((v) => v === 'expired')) {
    return {
      state: 'expired',
      summary: 'Your warranty has expired, so this visit may be chargeable. Our team will confirm.',
    };
  }
  return {
    state: 'needs_review',
    summary: 'Our team will confirm your warranty and come back to you.',
  };
}
