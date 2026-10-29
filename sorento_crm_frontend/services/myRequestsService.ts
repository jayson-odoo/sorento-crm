/**
 * My Requests from the CRM (PORTAL-P4-REQUESTS): a salesperson's own request forms over the CRM
 * session. The server mounts the portal's own routes at `/api/v1/my-requests` (same paths, bodies and
 * answers), so these mirror `app/(auth)/portal/lib/portal-client.ts` function for function, through
 * `apiFetch` instead of the portal token.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import {
  formCommentFormData,
  toFormComment,
  toFormCommentPostResult,
} from '@/services/formCommentsService';
import type { FormComment, FormCommentPostResult } from '@/types/formComments';
import type {
  PortalAttachment,
  PortalRevisionDraft,
  PortalRevisionEntry,
  PortalRevisionPolicy,
  PortalSubmissionDetail,
  RequestorOption,
} from '@/app/(auth)/portal/lib/portal-client';
import type { PriceTagRequestDetail } from '@/app/(protected)/dealer-kit/services/priceTagRequestService';
import type {
  PriceMode,
  PriceTagRequestLineInput,
  ProductCombosLookup,
} from '@/app/(auth)/portal/lib/price-tag-request-service';
import type { LinePricingLineInput, LinePricingResult } from '@/lib/dealer-kit/line-pricing-types';
import type { ChangeRequestPayload, ReviewComment } from '@/lib/dealer-kit/review-comments';
import { filenameFromContentDisposition, saveBlobAs } from '@/lib/save-blob';
import {
  designPayloadFromResponse,
  type TagSheetDesignPayload,
  type TagSheetDesignResponse,
} from '@/lib/dealer-kit/design-payload';

const BASE = '/api/v1/my-requests';

/** The four forms a salesperson writes from the CRM. */
export type MyRequestKind = 'stock_inquiry' | 'complaint' | 'purchase_request' | 'sponsorship_form';

const submissionUrl = (kind: MyRequestKind, id?: string) =>
  id ? `${BASE}/submissions/${kind}/${encodeURIComponent(id)}` : `${BASE}/submissions/${kind}`;

async function unwrap<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) throw new Error(await extractApiError(res, fallback));
  return (await res.json()) as T;
}

async function ensureOk(res: Response, fallback: string): Promise<void> {
  if (!res.ok && res.status !== 204) throw new Error(await extractApiError(res, fallback));
}

/**
 * A refusal keeps the portal's `{message, code, fields}` shape, so a caller can name an offending
 * line the way the portal form does (see `throwSubmissionError` in portal-client.ts).
 */
async function throwSubmissionError(res: Response, fallback: string): Promise<never> {
  const spare = res.clone();
  let body: { message?: unknown; detail?: unknown; code?: unknown } | null = null;
  try {
    body = (await spare.json()) as { message?: unknown; detail?: unknown; code?: unknown };
  } catch {
    body = null;
  }
  const message =
    typeof body?.message === 'string' && body.message ? body.message : await extractApiError(res, fallback);
  const code = typeof body?.code === 'string' ? body.code : null;
  const fields =
    typeof body?.detail === 'string' && body.detail
      ? body.detail.split(',').map((f) => f.trim()).filter(Boolean)
      : [];
  throw Object.assign(new Error(message), { code, fields });
}

export interface MyRequestDetail extends PortalSubmissionDetail {
  revision?: PortalRevisionPolicy;
  revision_draft?: PortalRevisionDraft | null;
  [key: string]: unknown;
}

export async function fetchSubmission(kind: MyRequestKind, id: string): Promise<MyRequestDetail> {
  return unwrap<MyRequestDetail>(await apiFetch(submissionUrl(kind, id)), 'Failed to load submission.');
}

export async function saveDraft(
  kind: MyRequestKind,
  fields: Record<string, unknown>,
  products?: Record<string, unknown>[],
  id?: string,
): Promise<MyRequestDetail> {
  const res = await apiFetch(submissionUrl(kind, id), {
    method: id ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fields, products }),
  });
  if (!res.ok) return throwSubmissionError(res, 'Failed to save draft.');
  return (await res.json()) as MyRequestDetail;
}

export async function submitDraft(
  kind: MyRequestKind,
  id: string,
  fields?: Record<string, unknown>,
  products?: Record<string, unknown>[],
): Promise<MyRequestDetail> {
  const body = fields || products ? JSON.stringify({ fields: fields || {}, products }) : undefined;
  const res = await apiFetch(`${submissionUrl(kind, id)}/submit`, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body,
  });
  if (!res.ok) return throwSubmissionError(res, 'Failed to submit.');
  return (await res.json()) as MyRequestDetail;
}

export async function deleteDraftSubmission(kind: MyRequestKind, id: string): Promise<void> {
  await ensureOk(await apiFetch(submissionUrl(kind, id), { method: 'DELETE' }), 'Failed to delete draft.');
}

export async function fetchRevisions(kind: MyRequestKind, id: string): Promise<PortalRevisionEntry[]> {
  const data = await unwrap<{ items?: PortalRevisionEntry[] }>(
    await apiFetch(`${submissionUrl(kind, id)}/revisions`),
    'Failed to load revision history.',
  );
  return data.items ?? [];
}

export interface ReviseSubmissionInput {
  reason: string;
  /** The revision_no the user was looking at. A mismatch is a 409. */
  expectedRevisionNo: number;
  fields: Record<string, unknown>;
  products?: Record<string, unknown>[];
}

export interface ReviseSubmissionResult {
  submission: MyRequestDetail;
  revision: PortalRevisionPolicy;
  revision_no: number;
}

export async function reviseSubmission(
  kind: MyRequestKind,
  id: string,
  input: ReviseSubmissionInput,
): Promise<ReviseSubmissionResult> {
  const res = await apiFetch(`${submissionUrl(kind, id)}/revise`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      reason: input.reason,
      expected_revision_no: input.expectedRevisionNo,
      fields: input.fields,
      products: input.products,
    }),
  });
  if (!res.ok) return throwSubmissionError(res, 'Failed to send revision.');
  return (await res.json()) as ReviseSubmissionResult;
}

export interface SaveRevisionDraftInput {
  reason?: string | null;
  baseRevisionNo: number;
  fields: Record<string, unknown>;
  products?: Record<string, unknown>[];
}

export async function saveRevisionDraft(
  kind: MyRequestKind,
  id: string,
  input: SaveRevisionDraftInput,
): Promise<PortalRevisionDraft> {
  const res = await apiFetch(`${submissionUrl(kind, id)}/revision-draft`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      reason: input.reason ?? null,
      base_revision_no: input.baseRevisionNo,
      fields: input.fields,
      products: input.products,
    }),
  });
  return unwrap<PortalRevisionDraft>(res, 'Failed to save draft.');
}

export async function discardRevisionDraft(kind: MyRequestKind, id: string): Promise<void> {
  await ensureOk(
    await apiFetch(`${submissionUrl(kind, id)}/revision-draft`, { method: 'DELETE' }),
    'Failed to discard draft.',
  );
}

export interface RequestorOptionsResult {
  items: RequestorOption[];
  hasMore: boolean;
}

/** Names only: the same eligible set the portal offers this contact, their own contact included. */
export async function fetchRequestorOptions(q?: string): Promise<RequestorOptionsResult> {
  const usp = new URLSearchParams();
  if (q && q.trim()) usp.set('q', q.trim());
  const qs = usp.toString();
  const data = await unwrap<{ items?: RequestorOption[]; has_more?: boolean }>(
    await apiFetch(`${BASE}/requestor-options${qs ? `?${qs}` : ''}`),
    'Failed to load requestor options.',
  );
  return { items: data.items ?? [], hasMore: Boolean(data.has_more) };
}

export async function fetchSubmissionComments(kind: MyRequestKind, id: string): Promise<FormComment[]> {
  const data = await unwrap<{ items?: Record<string, unknown>[] }>(
    await apiFetch(`${submissionUrl(kind, id)}/comments`),
    'Failed to load comments.',
  );
  return (data.items ?? []).map(toFormComment);
}

/** Their comment, as the submitter (multipart: body + 0..5 files), the portal's own path. */
export async function postSubmissionComment(
  kind: MyRequestKind,
  id: string,
  body: string,
  files: File[] = [],
  parentId?: string | null,
): Promise<FormCommentPostResult> {
  const res = await apiFetch(`${submissionUrl(kind, id)}/comments`, {
    method: 'POST',
    body: formCommentFormData(body, files, parentId),
  });
  return toFormCommentPostResult(await unwrap<Record<string, unknown>>(res, 'Failed to post the comment.'));
}

export async function editSubmissionComment(
  kind: MyRequestKind,
  id: string,
  commentId: string,
  body: string,
): Promise<void> {
  const res = await apiFetch(`${submissionUrl(kind, id)}/comments/${encodeURIComponent(commentId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ body }),
  });
  await ensureOk(res, 'Failed to save the comment.');
}

export async function deleteSubmissionComment(kind: MyRequestKind, id: string, commentId: string): Promise<void> {
  await ensureOk(
    await apiFetch(`${submissionUrl(kind, id)}/comments/${encodeURIComponent(commentId)}`, { method: 'DELETE' }),
    'Failed to delete the comment.',
  );
}

/** The kinds whose files ride the generic attachment routes: the four forms and (S5) the new product
 *  application, whose own router has no upload route, exactly as on the portal. */
export type MyRequestAttachmentKind = MyRequestKind | 'new_product_application' | 'price_tag_request';

export async function uploadAttachment(
  kind: MyRequestAttachmentKind,
  submissionId: string,
  file: File,
): Promise<PortalAttachment> {
  const form = new FormData();
  form.set('kind', kind);
  form.set('submission_id', submissionId);
  form.set('file', file, file.name);
  return unwrap<PortalAttachment>(await apiFetch(`${BASE}/attachments`, { method: 'POST', body: form }), 'Upload failed.');
}

export async function deleteAttachment(linkId: string): Promise<void> {
  await ensureOk(
    await apiFetch(`${BASE}/attachments/${encodeURIComponent(linkId)}`, { method: 'DELETE' }),
    'Failed to remove attachment.',
  );
}

/** Bytes of an attachment on their own request, keyed on the attachment id (as the portal's route). */
export function myRequestsAttachmentDownloadUrl(attachmentId: string): string {
  return `${BASE}/attachments/${encodeURIComponent(attachmentId)}/download`;
}

/** Save an attachment on their own request. Fetched through `apiFetch`, so an admin viewing as
 *  them sends the impersonation header; a plain link would fetch as the admin. */
export async function downloadMyRequestAttachment(attachmentId: string, filename: string): Promise<void> {
  const res = await apiFetch(myRequestsAttachmentDownloadUrl(attachmentId));
  if (!res.ok) throw new Error(await extractApiError(res, 'Download failed.'));
  saveBlobAs(await res.blob(), filename);
}

const jsonBody = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

// ---------------------------------------------------------------- Price Tag Request (S7)
// The portal's own price tag router at /api/v1/my-requests (same paths, bodies and answers as the
// portal). Its files go through the generic `/attachments` routes and its revise through the
// generic revision route, as on the portal.

const PRICE_TAG_URL = `${BASE}/submissions/price_tag_request`;

/** One line as the portal writes it (S7b): the item, how many tags, its package and parts, and its own
 *  promotion or typed price - the shared line editor's payload (`draftLinesPayload`). */
export type MyPriceTagLineWrite = PriceTagRequestLineInput;

export interface MyPriceTagWrite {
  debtor_code?: string | null;
  debtor_name?: string | null;
  needed_by_date?: string | null;
  notes?: string | null;
  price_mode?: PriceMode;
  print_by?: 'office' | 'self' | null;
  lines?: MyPriceTagLineWrite[];
}

/** The detail body plus the revision policy the portal hands back with it. */
export type MyPriceTagRequestDetail = PriceTagRequestDetail & {
  portal_draft_at?: string | null;
  /** The latest tag sheet export: what the proof viewer's Download PDF reads. */
  latest_export_status?: 'ready' | 'pending' | 'failed' | null;
  revision_no?: number;
  revision?: PortalRevisionPolicy | null;
};

export interface MyPriceTagDebtor {
  customer_id: string | null;
  customer_code: string | null;
  customer_name: string | null;
  debtor_code: string | null;
  debtor_name: string | null;
  source: string;
}

export interface MyPriceTagItem {
  kind: 'product' | 'product_set';
  id: string;
  code: string;
  name: string;
}

const priceTagUrl = (
  id: string,
  action?: 'submit' | 'approve' | 'request-changes' | 'review-comments' | 'design' | 'download' | 'collect' | 'revise',
) =>
  `${PRICE_TAG_URL}/${encodeURIComponent(id)}${action ? `/${action}` : ''}`;

export async function fetchMyPriceTagRequest(id: string): Promise<MyPriceTagRequestDetail> {
  return unwrap(await apiFetch(priceTagUrl(id)), 'Failed to load the price tag request');
}

export async function createMyPriceTagRequest(data: MyPriceTagWrite): Promise<MyPriceTagRequestDetail> {
  const res = await apiFetch(PRICE_TAG_URL, jsonBody('POST', data));
  if (!res.ok) await throwSubmissionError(res, 'Failed to save the price tag request');
  return (await res.json()) as MyPriceTagRequestDetail;
}

export async function updateMyPriceTagRequest(id: string, data: MyPriceTagWrite): Promise<MyPriceTagRequestDetail> {
  const res = await apiFetch(priceTagUrl(id), jsonBody('PUT', data));
  if (!res.ok) await throwSubmissionError(res, 'Failed to save the price tag request');
  return (await res.json()) as MyPriceTagRequestDetail;
}

export async function deleteMyPriceTagRequest(id: string): Promise<void> {
  await ensureOk(await apiFetch(priceTagUrl(id), { method: 'DELETE' }), 'Failed to delete the draft');
}

export async function submitMyPriceTagRequest(id: string): Promise<void> {
  const res = await apiFetch(priceTagUrl(id, 'submit'), { method: 'POST' });
  if (!res.ok) await throwSubmissionError(res, 'Failed to submit the price tag request');
}

/** The salesperson approves the proof marketing sent. */
export async function approveMyPriceTagRequest(id: string): Promise<void> {
  await ensureOk(await apiFetch(priceTagUrl(id, 'approve'), { method: 'POST' }), 'Failed to approve the proof');
}

/** The round's pinned change requests and general note, in one call (the portal's `requestChanges`). */
export async function requestMyPriceTagChanges(id: string, payload: ChangeRequestPayload): Promise<void> {
  await ensureOk(
    await apiFetch(priceTagUrl(id, 'request-changes'), jsonBody('POST', payload)),
    'Failed to send the change requests',
  );
}

/** Every change request sent on this design, all rounds. */
export async function fetchMyPriceTagReviewComments(id: string): Promise<ReviewComment[]> {
  return unwrap(await apiFetch(priceTagUrl(id, 'review-comments')), 'Failed to load the change requests');
}

/** The proof marketing sent, or null while there is none (the portal's `getPriceTagDesign`). */
export async function fetchMyPriceTagDesign(id: string): Promise<TagSheetDesignPayload | null> {
  const res = await apiFetch(priceTagUrl(id, 'design'));
  if (res.status === 404) return null;
  return designPayloadFromResponse(await unwrap<TagSheetDesignResponse>(res, 'Failed to load the design.'));
}

/** The latest completed tag sheet PDF, saved through the browser (the portal's `downloadPriceTagPdf`). */
export async function downloadMyPriceTagPdf(id: string): Promise<void> {
  const res = await apiFetch(priceTagUrl(id, 'download'));
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to download the PDF'));
  const blob = await res.blob();
  saveBlobAs(blob, filenameFromContentDisposition(res.headers.get('Content-Disposition')) || 'tag-sheet.pdf');
}

/** The salesperson has the printed tags in hand. */
export async function collectMyPriceTagRequest(id: string): Promise<void> {
  await ensureOk(await apiFetch(priceTagUrl(id, 'collect'), { method: 'POST' }), 'Failed to mark collected');
}

/** A revision of a submitted request: header fields plus the lines as products (the PTAG adapter). */
export async function reviseMyPriceTagRequest(
  id: string,
  input: { reason: string; expectedRevisionNo: number; fields: Record<string, unknown>; products: MyPriceTagLineWrite[] },
): Promise<void> {
  const res = await apiFetch(
    priceTagUrl(id, 'revise'),
    jsonBody('POST', {
      reason: input.reason,
      expected_revision_no: input.expectedRevisionNo,
      fields: input.fields,
      products: input.products,
    }),
  );
  if (!res.ok) await throwSubmissionError(res, 'Failed to send the revision');
}

/** Every debtor of every agent their contact is linked to (the portal's picker). */
export async function fetchMyPriceTagDebtors(): Promise<MyPriceTagDebtor[]> {
  return unwrap(await apiFetch(`${BASE}/lookups/debtors-for-agent`), 'Failed to load customers');
}

export async function searchMyPriceTagItems(q: string): Promise<MyPriceTagItem[]> {
  return unwrap(
    await apiFetch(`${BASE}/lookups/price-tag-items?q=${encodeURIComponent(q)}`),
    'Failed to search products',
  );
}

/** The catalogue packages a picked product is sold as, and whether its class is guarded (the portal's
 *  `lookupProductCombos`). */
export async function lookupMyProductCombos(productId: string): Promise<ProductCombosLookup> {
  return unwrap(
    await apiFetch(`${BASE}/lookups/product-combos/${encodeURIComponent(productId)}`),
    'Failed to load the packages for this product',
  );
}

/** One pricing call for every line, priced for this salesperson (`price_mode` is not sent, as on the portal). */
export async function lookupMyLinePricing(
  _priceMode: PriceMode,
  lines: LinePricingLineInput[],
): Promise<LinePricingResult[]> {
  return unwrap(await apiFetch(`${BASE}/lookups/line-pricing`, jsonBody('POST', { lines })), 'Failed to price these lines');
}
