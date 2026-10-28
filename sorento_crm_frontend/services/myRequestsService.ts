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
import type { SampleRequestCustomerHit } from '@/app/(auth)/portal/lib/sample-request-service';
import {
  SampleRequestError,
  type SampleRequestDetail,
  type SampleRequestProductHit,
  type SampleRequestWrite,
} from '@/types/sampleRequest';
import type {
  SalesOpportunityCustomerOptionsResponse,
  SalesOpportunityDetail,
  SalesOpportunitySavePayload,
} from '@/app/(protected)/sales/opportunities/types/salesOpportunity.types';

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

export async function uploadAttachment(kind: MyRequestKind, submissionId: string, file: File): Promise<PortalAttachment> {
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

// ---------------------------------------------------------------- Sample Request (S4)
// The portal's own sample request router, mounted at /api/v1/my-requests (same paths, bodies and
// answers as `app/(auth)/portal/lib/sample-request-service.ts`).

const SAMPLE_REQUEST_URL = `${BASE}/submissions/sample_request`;

/** A refusal that names a field arrives as `{message, code, details: {field}}`, as on the portal. */
async function sampleRequestResult<T>(res: Response, fallback: string): Promise<T> {
  if (res.ok) return (await res.json()) as T;
  const spare = res.clone();
  const message = await extractApiError(res, fallback);
  type Body = { code?: unknown; details?: { field?: unknown } };
  let body: Body | null = null;
  try {
    body = (await spare.json()) as Body;
  } catch {
    body = null;
  }
  throw new SampleRequestError(
    message,
    typeof body?.code === 'string' ? body.code : null,
    typeof body?.details?.field === 'string' ? body.details.field : null,
  );
}

const sampleRequestUrl = (id: string, action?: 'submit' | 'cancel') =>
  `${SAMPLE_REQUEST_URL}/${encodeURIComponent(id)}${action ? `/${action}` : ''}`;

/** The debtors their agent may raise a sample request for: exactly the set submit accepts. */
export async function fetchMySampleRequestCustomers(q: string): Promise<SampleRequestCustomerHit[]> {
  return sampleRequestResult<SampleRequestCustomerHit[]>(
    await apiFetch(`${BASE}/sample-request/customers?q=${encodeURIComponent(q)}`),
    'Failed to load customers',
  );
}

export async function searchMySampleRequestProducts(q: string): Promise<SampleRequestProductHit[]> {
  return sampleRequestResult<SampleRequestProductHit[]>(
    await apiFetch(`${BASE}/sample-request/products?q=${encodeURIComponent(q)}`),
    'Failed to search products',
  );
}

export async function createMySampleRequest(data: SampleRequestWrite): Promise<SampleRequestDetail> {
  return sampleRequestResult<SampleRequestDetail>(
    await apiFetch(SAMPLE_REQUEST_URL, { method: 'POST', body: JSON.stringify(data) }),
    'Failed to save the sample request',
  );
}

export async function updateMySampleRequest(id: string, data: SampleRequestWrite): Promise<SampleRequestDetail> {
  return sampleRequestResult<SampleRequestDetail>(
    await apiFetch(sampleRequestUrl(id), { method: 'PUT', body: JSON.stringify(data) }),
    'Failed to save the sample request',
  );
}

export async function submitMySampleRequest(id: string): Promise<SampleRequestDetail> {
  return sampleRequestResult<SampleRequestDetail>(
    await apiFetch(sampleRequestUrl(id, 'submit'), { method: 'POST' }),
    'Failed to submit the sample request',
  );
}

/** Only while Draft or Submitted, as on the portal; once the coordinator is on it, staff cancel. */
export async function cancelMySampleRequest(id: string): Promise<SampleRequestDetail> {
  return sampleRequestResult<SampleRequestDetail>(
    await apiFetch(sampleRequestUrl(id, 'cancel'), { method: 'POST' }),
    'Failed to cancel the sample request',
  );
}

// ---------------------------------------------------------------- Sales Opportunity (S6)
// The portal's own opportunity router at /api/v1/my-requests: the agent comes from their contact
// (a prospect gets the portal's default agent), never from the body.

const OPPORTUNITY_URL = `${BASE}/sales-opportunities`;

const jsonBody = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

/** The portal body: no agent (their contact decides it) and no sales order link (staff only). */
function withoutAgent(payload: SalesOpportunitySavePayload): SalesOpportunitySavePayload {
  const body = { ...payload };
  delete body.sales_agent_id;
  delete body.sales_order_id;
  return body;
}

export async function fetchMySalesOpportunityCustomerOptions(
  q: string,
): Promise<SalesOpportunityCustomerOptionsResponse> {
  const usp = new URLSearchParams();
  if (q) usp.set('q', q);
  return unwrap(await apiFetch(`${OPPORTUNITY_URL}/customer-options?${usp.toString()}`), 'Failed to search customers');
}

export async function createMySalesOpportunity(payload: SalesOpportunitySavePayload): Promise<SalesOpportunityDetail> {
  return unwrap(await apiFetch(OPPORTUNITY_URL, jsonBody('POST', withoutAgent(payload))), 'Failed to log opportunity');
}

export async function updateMySalesOpportunity(
  id: string,
  payload: SalesOpportunitySavePayload,
): Promise<SalesOpportunityDetail> {
  return unwrap(
    await apiFetch(`${OPPORTUNITY_URL}/${encodeURIComponent(id)}`, jsonBody('PATCH', withoutAgent(payload))),
    'Failed to save opportunity',
  );
}
