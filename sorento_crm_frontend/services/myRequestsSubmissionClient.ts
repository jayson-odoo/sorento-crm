/**
 * The portal form's client over the CRM session (PORTAL-P4-REQUESTS R1, form parity).
 *
 * A salesperson's create, edit and view of their own request renders the PORTAL's SubmissionForm
 * inside the CRM page (`components/common/MyRequestPortalForm`). That form reads every call through
 * an injected client (`app/(auth)/portal/lib/submission-client`); this is the CRM's: portal-client
 * function for function, through `apiFetch` against `/api/v1/my-requests`, where the server mounts
 * the portal's own routes (same paths, bodies and answers). The submission routes reuse
 * `myRequestsService`; the profile, lookups and AI extract are added here.
 *
 * Deletes are not here: the CRM parks them (D7), see `MyRequestPortalForm`.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import { myRequestStaffPath } from '@/lib/my-requests-staff-pages';
import * as myRequests from '@/services/myRequestsService';
import type { MyRequestAttachmentKind, MyRequestKind } from '@/services/myRequestsService';
import type {
  AIExtractResult,
  DebtorLookupItem,
  DOLookupFilters,
  DOLookupItem,
  LookupSetResult,
  PortalContact,
  PortalLandingKind,
  PortalSubmissionKind,
  PortalSubmissionNeighbours,
  ProductLookupItem,
  ProjectLookupItem,
} from '@/app/(auth)/portal/lib/portal-client';
import type { SubmissionApi, SubmissionPaths } from '@/app/(auth)/portal/lib/submission-client';

const BASE = '/api/v1/my-requests';
/** The portal prefix a preview item's bytes route carries (`portal-preview.toPreviewItem`). */
const PORTAL_BASE = '/api/v1/public/portal';

async function unwrap<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) throw new Error(await extractApiError(res, fallback));
  return (await res.json()) as T;
}

/** The four forms ride the generic routes; a wider portal kind is the server's to refuse. */
const asKind = (kind: PortalLandingKind) => kind as MyRequestKind;

export async function fetchMe(): Promise<PortalContact> {
  return unwrap<PortalContact>(await apiFetch(`${BASE}/me`), 'Failed to load profile.');
}

export async function fetchSubmissionNeighbours(
  kind: PortalLandingKind,
  id: string,
): Promise<PortalSubmissionNeighbours> {
  return unwrap<PortalSubmissionNeighbours>(
    await apiFetch(`${BASE}/submissions/${kind}/${encodeURIComponent(id)}/neighbours`),
    'Failed to load navigation.',
  );
}

export async function lookupProducts(q: string, limit = 20): Promise<ProductLookupItem[]> {
  return unwrap<ProductLookupItem[]>(
    await apiFetch(`${BASE}/lookups/products?q=${encodeURIComponent(q)}&limit=${limit}`),
    'Failed to load products.',
  );
}

export async function lookupDebtors(q: string, limit = 20, kind?: string): Promise<DebtorLookupItem[]> {
  const url =
    `${BASE}/lookups/debtors?q=${encodeURIComponent(q)}&limit=${limit}` +
    (kind ? `&kind=${encodeURIComponent(kind)}` : '');
  return unwrap<DebtorLookupItem[]>(await apiFetch(url), 'Failed to load debtors.');
}

export async function lookupProjects(q: string, limit = 20): Promise<ProjectLookupItem[]> {
  return unwrap<ProjectLookupItem[]>(
    await apiFetch(`${BASE}/lookups/projects?q=${encodeURIComponent(q)}&limit=${limit}`),
    'Failed to load projects.',
  );
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
  return unwrap<DOLookupItem[]>(
    await apiFetch(`${BASE}/lookups/delivery-orders?${params.toString()}`),
    'Failed to load delivery orders.',
  );
}

/**
 * `lookupSet` with its own cache, one per client: a set is read once per form, and the portal's
 * cache (`portal-client.lookupSet`) is never shared with the CRM's.
 */
function cachedLookupSet(): (setKey: string) => Promise<LookupSetResult> {
  const cache: Record<string, Promise<LookupSetResult>> = {};
  return (setKey) => {
    cache[setKey] ??= (async () => {
      const data = await unwrap<{ options?: LookupSetResult['options']; default_value?: string | null }>(
        await apiFetch(`${BASE}/lookups/sets/${encodeURIComponent(setKey)}`),
        'Failed to load lookup options.',
      );
      return { options: data?.options ?? [], defaultValue: data?.default_value ?? null };
    })().catch((e: unknown) => {
      delete cache[setKey];
      throw e;
    });
    return cache[setKey];
  };
}

export async function aiExtractFromFiles(formKey: string, files: File[]): Promise<AIExtractResult> {
  if (!files.length) throw new Error('Drop at least one file before extracting.');
  const form = new FormData();
  form.set('form_key', formKey);
  for (const file of files) form.append('files', file, file.name);
  return unwrap<AIExtractResult>(
    await apiFetch(`${BASE}/ai-extract`, { method: 'POST', body: form }),
    'AI extract failed.',
  );
}

/**
 * The bytes of an attachment on their own request. A preview item names the portal's route
 * (`portal-preview.toPreviewItem`); the same route lives under my-requests, keyed on the same
 * attachment id, and `apiFetch` sends the session (and the impersonation header).
 */
export async function fetchPortalAttachmentBytes(downloadUrl: string): Promise<Response> {
  const url = downloadUrl.startsWith(`${PORTAL_BASE}/`)
    ? `${BASE}${downloadUrl.slice(PORTAL_BASE.length)}`
    : downloadUrl;
  return apiFetch(url);
}

/** The staff pages a salesperson's own request lives on (`MY_REQUEST_STAFF_PAGES`). */
export const myRequestsPaths: SubmissionPaths = {
  home: (kind: PortalSubmissionKind) => myRequestStaffPath(kind) ?? '/',
  detail: (kind: PortalSubmissionKind, id: string) =>
    `${myRequestStaffPath(kind) ?? ''}/${encodeURIComponent(id)}`,
  duplicate: (kind: PortalSubmissionKind, id: string) =>
    `${myRequestStaffPath(kind) ?? ''}/new?from=${encodeURIComponent(id)}`,
};

/** portal-client, function for function, over `/api/v1/my-requests`. A fresh one per form: its
 *  lookup sets are cached per client. */
export const createMyRequestsSubmissionApi = (): SubmissionApi => ({
  fetchMe,
  fetchSubmission: (kind, id) => myRequests.fetchSubmission(asKind(kind), id),
  fetchSubmissionNeighbours,
  fetchRequestorOptions: myRequests.fetchRequestorOptions,
  lookupProducts,
  lookupDebtors,
  lookupProjects,
  lookupDeliveryOrders,
  lookupSet: cachedLookupSet(),
  saveDraft: (kind, fields, products, id) => myRequests.saveDraft(asKind(kind), fields, products, id),
  submitDraft: (kind, id, fields, products) => myRequests.submitDraft(asKind(kind), id, fields, products),
  deleteDraftSubmission: (kind, id) => myRequests.deleteDraftSubmission(asKind(kind), id),
  saveRevisionDraft: (kind, id, input) => myRequests.saveRevisionDraft(asKind(kind), id, input),
  discardRevisionDraft: (kind, id) => myRequests.discardRevisionDraft(asKind(kind), id),
  fetchRevisions: (kind, id) => myRequests.fetchRevisions(asKind(kind), id),
  reviseSubmission: (kind, id, input) => myRequests.reviseSubmission(asKind(kind), id, input),
  uploadAttachment: (kind, id, file) => myRequests.uploadAttachment(kind as MyRequestAttachmentKind, id, file),
  deleteAttachment: myRequests.deleteAttachment,
  fetchSubmissionComments: (kind, id) => myRequests.fetchSubmissionComments(asKind(kind), id),
  postSubmissionComment: (kind, id, body, files, parentId) =>
    myRequests.postSubmissionComment(asKind(kind), id, body, files, parentId),
  editSubmissionComment: (kind, id, commentId, body) =>
    myRequests.editSubmissionComment(asKind(kind), id, commentId, body),
  deleteSubmissionComment: (kind, id, commentId) =>
    myRequests.deleteSubmissionComment(asKind(kind), id, commentId),
  aiExtractFromFiles,
  portalAttachmentDownloadUrl: myRequests.myRequestsAttachmentDownloadUrl,
  fetchPortalAttachmentBytes,
});
