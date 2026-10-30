/**
 * Portal-side new product application service (NEW-PRODUCT-APP).
 *
 * Calls `/api/v1/public/portal/submissions/new_product_application` through `portalFetch`.
 * The shapes live in `types/newProductApplication.ts`, shared with the staff feature.
 *
 * `makeNewProductApplicationService(fetcher)` holds the calls (PORTAL-P4-REQUESTS R3, form
 * parity); the named exports are the portal's instance over `portalFetch`. The CRM builds one over
 * its session (`services/myRequestsSubmissionClient.ts`), so a salesperson's form makes the
 * portal's calls.
 */
import { extractApiError } from '@/lib/api-client';
import { filenameFromContentDisposition } from '@/app/(protected)/project-sales/_shared/services/fileDownload';
import { saveBlobAs } from '@/lib/save-blob';
import {
  NewProductApplicationError,
  type NewProductApplicationDetail,
  type NewProductApplicationPrefill,
  type NewProductApplicationSummary,
  type NewProductApplicationWrite,
} from '@/types/newProductApplication';
import { portalFetch, type PortalSubmissionSummary } from './portal-client';

const BASE = '/api/v1/public/portal/submissions/new_product_application';
const OWN = '/api/v1/public/portal/new-product-application';

/** A refusal that names a field arrives as `{message, code, details: {field}}`. */
async function unwrap<T>(res: Response, fallback: string): Promise<T> {
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
  throw new NewProductApplicationError(
    message,
    typeof body?.code === 'string' ? body.code : null,
    typeof body?.details?.field === 'string' ? body.details.field : null,
  );
}

const JSON_HEADERS = { 'Content-Type': 'application/json' };
const at = (id: string) => encodeURIComponent(id);

/** One of the contact's own responded stock inquiries (the "start from" picker). */
export interface PortalInquiryHit {
  id: string;
  inquiry_number: string | null;
  product_code: string | null;
  item_description: string | null;
  project_name: string | null;
  purchasing_response: string | null;
  last_responded_at: string | null;
}

export interface PortalLookupHit {
  id: string;
  code: string;
  name: string;
}

export type PortalLookupKind = 'brands';

export interface PortalCustomerHit {
  customer_id: string;
  customer_code: string;
  debtor_name: string;
}

export function makeNewProductApplicationService(fetcher: typeof portalFetch) {
  async function listMyRespondedInquiries(): Promise<PortalInquiryHit[]> {
    const res = await fetcher(`${OWN}/inquiries`);
    return unwrap<PortalInquiryHit[]>(res, 'Failed to load your stock inquiries');
  }

  async function getNewProductApplicationPrefill(
    stockInquiryId: string,
  ): Promise<NewProductApplicationPrefill> {
    const res = await fetcher(
      `${OWN}/prefill?stock_inquiry_id=${at(stockInquiryId)}`,
    );
    return unwrap<NewProductApplicationPrefill>(
      res,
      'Failed to load the stock inquiry',
    );
  }

  async function lookupNewProductApplication(
    kind: PortalLookupKind,
    q: string,
  ): Promise<PortalLookupHit[]> {
    const res = await fetcher(
      `${OWN}/lookups/${kind}?q=${encodeURIComponent(q)}`,
    );
    return unwrap<PortalLookupHit[]>(res, 'Failed to load the list');
  }

  async function lookupNewProductApplicationCustomers(
    q: string,
  ): Promise<PortalCustomerHit[]> {
    const res = await fetcher(`${OWN}/customers?q=${encodeURIComponent(q)}`);
    return unwrap<PortalCustomerHit[]>(res, 'Failed to load customers');
  }

  async function listNewProductApplications(
    q?: string,
  ): Promise<NewProductApplicationSummary[]> {
    const usp = new URLSearchParams();
    if (q && q.trim()) usp.set('q', q.trim());
    const qs = usp.toString();
    const res = await fetcher(qs ? `${BASE}?${qs}` : BASE);
    const page = await unwrap<{ data: NewProductApplicationSummary[] }>(
      res,
      'Failed to load applications',
    );
    return page.data ?? [];
  }

  /** The landing card shape: number first, customer on the second line. */
  async function listNewProductApplicationsAsSummaries(
    q?: string,
  ): Promise<PortalSubmissionSummary[]> {
    const rows = await listNewProductApplications(q);
    return rows.map((r) => {
      const editable = r.status === 'draft' || r.status === 'rejected';
      return {
        id: r.id,
        kind: 'new_product_application' as const,
        title: r.first_line || r.customer_name || r.application_no,
        document_number: r.application_no,
        reference: null,
        status: r.status,
        status_label: r.status_label,
        is_editable: editable,
        is_draft: r.status === 'draft',
        created_at: r.created_at,
        customer_name: r.customer_name,
        project_title: r.project_name,
      };
    });
  }

  async function getNewProductApplication(
    id: string,
  ): Promise<NewProductApplicationDetail> {
    const res = await fetcher(`${BASE}/${at(id)}`);
    return unwrap<NewProductApplicationDetail>(
      res,
      'Failed to load the application',
    );
  }

  async function createNewProductApplication(
    data: NewProductApplicationWrite,
  ): Promise<NewProductApplicationDetail> {
    const res = await fetcher(BASE, {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify(data),
    });
    return unwrap<NewProductApplicationDetail>(
      res,
      'Failed to save the application',
    );
  }

  async function updateNewProductApplication(
    id: string,
    data: NewProductApplicationWrite,
  ): Promise<NewProductApplicationDetail> {
    const res = await fetcher(`${BASE}/${at(id)}`, {
      method: 'PUT',
      headers: JSON_HEADERS,
      body: JSON.stringify(data),
    });
    return unwrap<NewProductApplicationDetail>(
      res,
      'Failed to save the application',
    );
  }

  const move = async (
    id: string,
    verb: string,
    fallback: string,
    body?: unknown,
  ) =>
    unwrap<NewProductApplicationDetail>(
      await fetcher(`${BASE}/${at(id)}/${verb}`, {
        method: 'POST',
        ...(body === undefined
          ? {}
          : { headers: JSON_HEADERS, body: JSON.stringify(body) }),
      }),
      fallback,
    );

  const submitNewProductApplication = (id: string) =>
    move(id, 'submit', 'Failed to submit the application');
  const reviseNewProductApplication = (id: string, reason: string) =>
    move(id, 'revise', 'Failed to revise the application', { reason });
  const cancelNewProductApplication = (id: string, reason?: string) =>
    move(
      id,
      'cancel',
      'Failed to cancel the application',
      reason ? { reason } : {},
    );

  /** The paper sheet as a workbook; the name comes from the server so file and sheet agree. */
  async function downloadNewProductApplicationExcel(
    id: string,
  ): Promise<void> {
    const res = await fetcher(`${BASE}/${at(id)}/download`);
    if (!res.ok) await unwrap<never>(res, 'Failed to download the application');
    const filename =
      filenameFromContentDisposition(res.headers.get('Content-Disposition')) ??
      'new-product-application.xlsx';
    saveBlobAs(await res.blob(), filename);
  }

  return {
    listMyRespondedInquiries,
    getNewProductApplicationPrefill,
    lookupNewProductApplication,
    lookupNewProductApplicationCustomers,
    listNewProductApplications,
    listNewProductApplicationsAsSummaries,
    getNewProductApplication,
    createNewProductApplication,
    updateNewProductApplication,
    submitNewProductApplication,
    reviseNewProductApplication,
    cancelNewProductApplication,
    downloadNewProductApplicationExcel,
  };
}

export type NewProductApplicationService = ReturnType<
  typeof makeNewProductApplicationService
>;

export const {
  listMyRespondedInquiries,
  getNewProductApplicationPrefill,
  lookupNewProductApplication,
  lookupNewProductApplicationCustomers,
  listNewProductApplications,
  listNewProductApplicationsAsSummaries,
  getNewProductApplication,
  createNewProductApplication,
  updateNewProductApplication,
  submitNewProductApplication,
  reviseNewProductApplication,
  cancelNewProductApplication,
  downloadNewProductApplicationExcel,
} = makeNewProductApplicationService(portalFetch);
