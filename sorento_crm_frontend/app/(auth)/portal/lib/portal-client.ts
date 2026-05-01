/**
 * Portal API client — token-scoped, no NextAuth session.
 *
 * The token is stored in sessionStorage and sent as `X-Portal-Token` on every
 * request. On 401 the caller is responsible for redirecting to /portal/verify.
 */
import { extractApiError } from '@/lib/api-client';

const TOKEN_KEY = 'sorento.portalToken';

export type PortalSubmissionKind =
  | 'complaint'
  | 'stock_inquiry'
  | 'purchase_request'
  | 'sponsorship_form';

export interface PortalContact {
  contact_id: string;
  space_id: string;
  name: string | null;
  phone_number: string | null;
  expires_at: string;
}

export interface PortalSubmissionSummary {
  id: string;
  kind: PortalSubmissionKind;
  title: string;
  reference: string | null;
  status: string;
  approval_status?: string | null;
  rejection_reason?: string | null;
  is_editable: boolean;
  is_draft: boolean;
  created_at: string | null;
}

export interface PortalAttachment {
  link_id: string;
  attachment_id: string;
  filename: string | null;
  size: number | null;
  url: string | null;
  uploaded_at?: string | null;
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

export function readPortalToken(): string | null {
  if (typeof window === 'undefined') return null;
  return window.sessionStorage.getItem(TOKEN_KEY);
}

export function writePortalToken(token: string): void {
  if (typeof window === 'undefined') return;
  window.sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearPortalToken(): void {
  if (typeof window === 'undefined') return;
  window.sessionStorage.removeItem(TOKEN_KEY);
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

export async function fetchSubmissions(kind: PortalSubmissionKind): Promise<PortalSubmissionSummary[]> {
  const res = await portalFetch(`/api/v1/public/portal/submissions?type=${encodeURIComponent(kind)}`);
  const data = await unwrap<{ items: PortalSubmissionSummary[] }>(res, 'Failed to load submissions.');
  return data.items ?? [];
}

export async function fetchSubmission(
  kind: PortalSubmissionKind,
  id: string
): Promise<PortalSubmissionDetail> {
  const res = await portalFetch(`/api/v1/public/portal/submissions/${kind}/${encodeURIComponent(id)}`);
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

export async function uploadAttachment(
  kind: PortalSubmissionKind,
  submissionId: string,
  file: File
): Promise<PortalAttachment> {
  const form = new FormData();
  form.set('kind', kind);
  form.set('submission_id', submissionId);
  form.set('file', file);
  const res = await portalFetch('/api/v1/public/portal/attachments', { method: 'POST', body: form });
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

export const SUBMISSION_LABELS: Record<PortalSubmissionKind, string> = {
  complaint: 'Complaint',
  stock_inquiry: 'Stock Inquiry',
  purchase_request: 'Purchase Request',
  sponsorship_form: 'Sponsorship Form',
};
