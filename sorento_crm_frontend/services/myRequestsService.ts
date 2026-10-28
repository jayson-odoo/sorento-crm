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
