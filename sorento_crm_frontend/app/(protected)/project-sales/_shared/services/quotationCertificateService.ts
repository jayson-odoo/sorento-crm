import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { PageBox } from '@/components/common/pdf-viewer/box-geometry';

/**
 * The Certification tab of a quotation document (QUOTE-CERT-TAB).
 *
 *   GET    .../quotation-documents/{id}/certificates                       -> CertificateList
 *   POST   .../certificates                                                -> CertificateRow (201)
 *   GET    .../certificates/{certificateId}                                -> CertificateDetail
 *   GET    .../certificates/{certificateId}/file                           -> the PDF
 *   PUT    .../certificates/{certificateId}/boxes                          -> CertificateDetail
 *   DELETE .../certificates/{certificateId}/boxes?scope=quote              -> CertificateDetail
 *   PATCH  .../certificates/{certificateId}                                -> CertificateRow
 *   POST   .../certificates/export                                         -> { download_id }
 *
 * Remove is a pending action (`quotation_certificate.remove`), not a route.
 */
const BASE = '/api/v1/project-sales';

export type CertificateValidity = 'valid' | 'expiring' | 'expired' | 'unknown';

export type MarkedState =
  | 'found'
  | 'edited'
  | 'none'
  | 'no_text'
  | 'not_found'
  | 'no_file'
  | 'code_needed'
  | 'not_on_certificate';

export type ProductState =
  | 'found'
  | 'edited'
  /** CERT-TAB-UX: marked by its code, but its box was deleted (for this quote or as default). */
  | 'unmarked'
  | 'not_found'
  | 'no_text'
  | 'code_needed';

export type CertificateBox = PageBox;

export interface CertificateRow {
  certificate_id: string;
  also_filed_as: { certificate_id: string; scheme: string; certificate_number: string }[];
  scheme: string;
  certificate_number: string;
  title: string | null;
  certifying_body: string | null;
  valid_until: string | null;
  validity_state: CertificateValidity;
  source: 'auto' | 'manual';
  products: { product_id: string; product_code: string }[];
  marked: { count: number; state: MarkedState };
  send_to_customer: boolean;
  has_file: boolean;
  verified: boolean;
}

export interface CertificateList {
  can_edit: boolean;
  /** Edit right and the register's view right: the Add certificate button. */
  can_add: boolean;
  can_edit_defaults: boolean;
  items: CertificateRow[];
}

export interface CertificateProductDetail {
  product_id: string;
  product_code: string;
  coverage_id: string;
  model_code: string | null;
  model_code_source: 'ai' | 'manual' | null;
  code_used: string | null;
  number_only: boolean;
  state: ProductState;
}

export interface CertificateDetail extends CertificateRow {
  revision_id: string | null;
  page_count: number | null;
  has_text: boolean;
  can_edit: boolean;
  can_edit_defaults: boolean;
  box_source: 'quote' | 'default';
  boxes: CertificateBox[];
  products: CertificateProductDetail[];
}

export type BoxScope = 'quote' | 'default';

function url(projectId: string, documentId: string, suffix = '') {
  return `${BASE}/projects/${projectId}/quotation-documents/${documentId}/certificates${suffix}`;
}

const JSON_HEADERS = { 'Content-Type': 'application/json' };

async function read<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) throw new Error(await extractApiError(response, fallback));
  return response.json();
}

export async function listQuotationCertificates(
  projectId: string,
  documentId: string,
): Promise<CertificateList> {
  return read(await apiFetch(url(projectId, documentId)), 'Could not load the certificates');
}

export async function addQuotationCertificate(
  projectId: string,
  documentId: string,
  certificateId: string,
): Promise<CertificateRow> {
  return read(
    await apiFetch(url(projectId, documentId), {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify({ certificate_id: certificateId }),
    }),
    'Could not add the certificate',
  );
}

export async function getQuotationCertificate(
  projectId: string,
  documentId: string,
  certificateId: string,
): Promise<CertificateDetail> {
  return read(
    await apiFetch(url(projectId, documentId, `/${certificateId}`)),
    'Could not load the certificate',
  );
}

export async function fetchQuotationCertificateFile(
  projectId: string,
  documentId: string,
  certificateId: string,
): Promise<ArrayBuffer> {
  const response = await apiFetch(url(projectId, documentId, `/${certificateId}/file`));
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not load the file'));
  return response.arrayBuffer();
}

export async function saveQuotationCertificateBoxes(
  projectId: string,
  documentId: string,
  certificateId: string,
  scope: BoxScope,
  boxes: CertificateBox[],
): Promise<CertificateDetail> {
  return read(
    await apiFetch(url(projectId, documentId, `/${certificateId}/boxes`), {
      method: 'PUT',
      headers: JSON_HEADERS,
      body: JSON.stringify({ scope, boxes }),
    }),
    'Could not save the boxes',
  );
}

export async function resetQuotationCertificateBoxes(
  projectId: string,
  documentId: string,
  certificateId: string,
): Promise<CertificateDetail> {
  return read(
    await apiFetch(url(projectId, documentId, `/${certificateId}/boxes?scope=quote`), {
      method: 'DELETE',
    }),
    'Could not reset the boxes',
  );
}

export async function setQuotationCertificateSend(
  projectId: string,
  documentId: string,
  certificateId: string,
  sendToCustomer: boolean | null,
): Promise<CertificateRow> {
  return read(
    await apiFetch(url(projectId, documentId, `/${certificateId}`), {
      method: 'PATCH',
      headers: JSON_HEADERS,
      body: JSON.stringify({ send_to_customer: sendToCustomer }),
    }),
    'Could not update the certificate',
  );
}

export async function queueQuotationCertificatesPdf(
  projectId: string,
  documentId: string,
  issueId: string | null,
): Promise<{ download_id: string }> {
  return read(
    await apiFetch(url(projectId, documentId, '/export'), {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify({ issue_id: issueId }),
    }),
    'Could not queue the certificates PDF',
  );
}
