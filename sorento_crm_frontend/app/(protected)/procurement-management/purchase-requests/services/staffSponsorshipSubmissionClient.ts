/**
 * The salesperson's sponsorship form, written by staff (PROJECT-STAGE-ACTIONS).
 *
 * Owner rule: CRM forms = portal forms, one component. A project's Sponsorship stage opens the
 * portal `SubmissionForm` (kind `sponsorship_form`) for everyone. A salesperson limited to their
 * own rows writes through /api/v1/my-requests (`MyRequestPortalForm`). Staff and admins cannot
 * (that route refuses them by design), so this client gives the same form the staff routes:
 *
 * - Save draft: the staff create / update (`/procurement/purchase-requests`, a `draft`).
 * - Submit: save, then `POST /purchase-requests/{id}/submit`, which runs the portal's submit rules
 *   and side effects for staff (`PortalService.submit_staff_request`).
 * - Profile (`fetchMe`): the PROJECT SALESPERSON's contact, so Requested by defaults to them and
 *   the form is written on their behalf.
 * - Lookups: the staff pickers the staff form already uses (customers, products, projects,
 *   lookup sets, requestor contacts).
 *
 * Only creating a new form from a project is served; the form's other calls answer plainly.
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import { getLookupOptionsByBinding, getLookupSetOptions } from '@/lib/lookupBindingService';
import type {
  DebtorLookupItem,
  LookupSetResult,
  PortalAttachment,
  PortalContact,
  PortalLandingKind,
  PortalSubmissionDetail,
  ProductLookupItem,
  ProjectLookupItem,
} from '@/app/(auth)/portal/lib/portal-client';
import type { SubmissionClient, SubmissionPaths } from '@/app/(auth)/portal/lib/submission-client';
import { getRequestorSelectOptions } from '@/app/(protected)/master-data-management/shared/services/requestorSelectService';
import { lookupCustomersForRequest } from './customerLookupService';

const BASE = '/api/v1/procurement/purchase-requests';
const SPONSORSHIP_PAGES = '/procurement-management/sponsorship-forms';

/** The project the form is written from: its salesperson and where Cancel / Submit go back to. */
export interface StaffSponsorshipProject {
  id: string;
  owner_name?: string | null;
  owner_contact_id?: string | null;
  /** That contact's name, which the saved form's Requested by prints. */
  owner_contact_name?: string | null;
}

async function unwrap<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) throw new Error(await extractApiError(res, fallback));
  return (await res.json()) as T;
}

/** The staff create's error answers as the form expects them: a sponsorship line refusal names
 *  its line (`detail: "line:0"`), which the form turns into "Line 1: ...". */
async function throwSaveError(res: Response, fallback: string): Promise<never> {
  let fields: string[] | undefined;
  let lineMessage: string | undefined;
  try {
    const body = await res.clone().json();
    if (typeof body?.detail === 'string' && body.detail.startsWith('line:')) {
      fields = [body.detail];
      // `detail` is the line reference here; the words are in `message`.
      if (typeof body.message === 'string') lineMessage = body.message;
    }
  } catch {
    // Not JSON: the message alone.
  }
  const message = lineMessage ?? (await extractApiError(res, fallback));
  const error = new Error(message) as Error & { fields?: string[] };
  if (fields) error.fields = fields;
  throw error;
}

const unavailable = (what: string) => () =>
  Promise.reject(new Error(`${what} is not available while writing a form for a project.`));

/** The form's fields and lines as the staff body: the same names, the type fixed, and the
 *  salesperson as the form's contact (they keep receiving its updates, as on their own form). */
function staffBody(fields: Record<string, unknown>, products?: Record<string, unknown>[]) {
  const requestor = typeof fields.requested_by_contact_id === 'string' ? fields.requested_by_contact_id : null;
  return {
    ...fields,
    request_type: 'sponsorship_form',
    ...(requestor ? { contact_id: requestor } : {}),
    ...(products ? { products } : {}),
  };
}

async function save(
  fields: Record<string, unknown>,
  products: Record<string, unknown>[] | undefined,
  id?: string,
): Promise<PortalSubmissionDetail> {
  const res = await apiFetch(id ? `${BASE}/${encodeURIComponent(id)}` : BASE, {
    method: id ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(staffBody(fields, products)),
  });
  if (!res.ok) return throwSaveError(res, 'Failed to save draft.');
  return (await res.json()) as PortalSubmissionDetail;
}

async function uploadAttachment(
  _kind: PortalLandingKind,
  submissionId: string,
  file: File,
): Promise<PortalAttachment> {
  const form = new FormData();
  form.append('file', file, file.name);
  // A second "quote.pdf" is kept as its own file, never a 409 mid-submit.
  form.append('on_conflict', 'copy');
  const uploaded = await unwrap<{ id: string; original_filename?: string | null; file_size_bytes?: number | null }>(
    await apiFetch('/api/v1/resource-management/attachments', { method: 'POST', body: form }),
    'Upload failed.',
  );
  const link = await unwrap<{ id: string }>(
    await apiFetch(`${BASE}/${encodeURIComponent(submissionId)}/attachments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ attachment_id: uploaded.id }),
    }),
    'Failed to attach the file.',
  );
  return {
    link_id: link.id,
    attachment_id: uploaded.id,
    filename: uploaded.original_filename ?? file.name,
    size: uploaded.file_size_bytes ?? file.size,
    url: null,
    uploader_kind: 'user',
    can_unlink: false,
  };
}

async function lookupProducts(q: string, limit = 20): Promise<ProductLookupItem[]> {
  const usp = new URLSearchParams({ limit: String(limit), offset: '0' });
  if (q.trim()) usp.set('query', q.trim());
  const body = await unwrap<{ data?: { id: string; product_code: string; product_name: string | null }[] }>(
    await apiFetch(`/api/v1/master-data/products/select?${usp.toString()}`),
    'Failed to load products.',
  );
  return (body.data ?? []).map((p) => ({
    product_id: p.id,
    product_code: p.product_code,
    product_name: p.product_name,
    category_id: null,
  }));
}

async function lookupDebtors(q: string): Promise<DebtorLookupItem[]> {
  const rows = await lookupCustomersForRequest(q);
  return rows.map((row) => ({
    customer_id: row.customer_id,
    debtor_name: row.debtor_name,
    customer_code: row.customer_code,
    sales_type: row.sales_type,
  }));
}

async function lookupProjects(q: string, limit = 20): Promise<ProjectLookupItem[]> {
  const usp = buildDataGridParams(
    {
      pageIndex: 0,
      pageSize: limit,
      sorting: [{ id: 'updated_at', desc: true }],
      searchQuery: q.trim(),
    },
    // A registration waiting for approval is not a project to link yet (PROJECT-REG-PORTAL R4).
    { approved_only: 'true' },
  );
  const body = await unwrap<{ data?: { id: string; project_code: string | null; title: string; name?: string | null }[] }>(
    await apiFetch(`/api/v1/project-sales/projects/?${usp.toString()}`),
    'Failed to load projects.',
  );
  return (body.data ?? []).map((p) => ({
    id: p.id,
    project_code: p.project_code ?? '',
    title: p.title,
    name: p.name ?? null,
  }));
}

/** The sets this form reads, by the `purchase_requests` column each is bound to: the binding
 *  carries the admin's "Default (new forms)", which the salesperson's form pre-selects too. */
const SET_BINDINGS: Record<string, string> = {
  procurement_sales_type: 'sales_type',
  procurement_sponsor_subject: 'sponsor_subject',
};

/** One fetch per set per form, as the portal client caches it. */
function cachedLookupSet(): (setKey: string) => Promise<LookupSetResult> {
  const cache: Record<string, Promise<LookupSetResult>> = {};
  const load = async (setKey: string): Promise<LookupSetResult> => {
    const column = SET_BINDINGS[setKey];
    if (column) {
      const bound = await getLookupOptionsByBinding('purchase_requests', column);
      return {
        options: bound.options.filter((o) => o.is_active !== false).map((o) => ({ value: o.value, label: o.label })),
        defaultValue: bound.default_value ?? null,
      };
    }
    const options = await getLookupSetOptions(setKey);
    return {
      options: options.filter((o) => o.is_active !== false).map((o) => ({ value: o.value, label: o.label })),
      defaultValue: null,
    };
  };
  return (setKey) => {
    cache[setKey] ??= load(setKey).catch((e: unknown) => {
      delete cache[setKey];
      throw e;
    });
    return cache[setKey];
  };
}

/** Where a project's sponsorship form goes when it is done or cancelled: back to the project's
 *  Sponsorship Form tab. The salesperson's and staff's alike. */
export function projectSponsorshipPaths(projectId: string): SubmissionPaths {
  const back = `/project-sales/${encodeURIComponent(projectId)}?tab=sponsorships`;
  return {
    home: () => back,
    new: () => `${SPONSORSHIP_PAGES}/new?project_id=${encodeURIComponent(projectId)}`,
    detail: (_kind, id) => `${SPONSORSHIP_PAGES}/${encodeURIComponent(id)}`,
    duplicate: (_kind, id) => `${SPONSORSHIP_PAGES}/new?from=${encodeURIComponent(id)}`,
    revise: (_kind, id) => `${SPONSORSHIP_PAGES}/${encodeURIComponent(id)}`,
  };
}

export function createStaffSponsorshipClient(project: StaffSponsorshipProject): SubmissionClient {
  const me: PortalContact = {
    contact_id: project.owner_contact_id ?? '',
    space_id: '',
    // The contact's name, as the saved form shows Requested by, never the user's.
    name: project.owner_contact_name ?? null,
    phone_number: null,
    expires_at: '',
    // As for an unflagged salesperson: the project the form starts with is shown by the form
    // itself (a seeded field is always shown), so both paths show the same fields.
    requires_registered_project: false,
  };
  return {
    fetchMe: async () => me,
    fetchSubmissions: unavailable('The list'),
    fetchSubmission: unavailable('Copying a form'),
    fetchSubmissionNeighbours: unavailable('Record navigation'),
    fetchRequestorOptions: async (q?: string) => {
      const { items, has_more } = await getRequestorSelectOptions({
        q,
        includeIds: [project.owner_contact_id],
      });
      return { items, hasMore: has_more };
    },
    lookupProducts,
    lookupDebtors,
    lookupProjects,
    lookupDeliveryOrders: async () => [],
    lookupSet: cachedLookupSet(),
    saveDraft: (_kind, fields, products, id) => save(fields, products, id),
    submitDraft: async (_kind, id, fields, products) => {
      if (fields || products) await save(fields ?? {}, products, id);
      const res = await apiFetch(`${BASE}/${encodeURIComponent(id)}/submit`, { method: 'POST' });
      if (!res.ok) return throwSaveError(res, 'Failed to submit.');
      return (await res.json()) as PortalSubmissionDetail;
    },
    deleteDraftSubmission: unavailable('Deleting a draft'),
    saveRevisionDraft: unavailable('A revision'),
    discardRevisionDraft: unavailable('A revision'),
    fetchRevisions: async () => [],
    reviseSubmission: unavailable('A revision'),
    uploadAttachment,
    deleteAttachment: unavailable('Removing a file'),
    fetchSubmissionComments: async () => [],
    postSubmissionComment: unavailable('Comments'),
    editSubmissionComment: unavailable('Comments'),
    deleteSubmissionComment: unavailable('Comments'),
    aiExtractFromFiles: unavailable('Reading a file'),
    portalAttachmentDownloadUrl: () => '',
    fetchPortalAttachmentBytes: unavailable('Previewing a file'),
    getPriceTagDesign: async () => null,
    paths: projectSponsorshipPaths(project.id),
    embedded: true,
    aiExtract: false,
  } as SubmissionClient;
}
