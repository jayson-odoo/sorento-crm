import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * The quotation DOCUMENT: one letterhead carrying several priced scopes.
 *
 * Contract, matching `app/api/v1/projects/quotation_documents.py` exactly:
 *
 *   GET    /projects/{projectId}/quotation-documents                       -> ListEnvelope<QuotationDocument>
 *   POST   /projects/{projectId}/quotation-documents                       -> QuotationDocument (201)
 *   GET    /projects/{projectId}/quotation-documents/{id}                  -> QuotationDocument
 *   PATCH  /projects/{projectId}/quotation-documents/{id}                  -> QuotationDocument
 *   DELETE /projects/{projectId}/quotation-documents/{id}                  -> 204, 422 once issued
 *   POST   /projects/{projectId}/quotation-documents/{id}/scopes           -> QuotationScope (201)
 *   PATCH  /projects/{projectId}/quotation-documents/{id}/scopes/{scopeId} -> QuotationScope
 *   POST   /projects/{projectId}/quotation-documents/{id}/issue            -> QuotationIssue (201)
 *   GET    /projects/{projectId}/quotation-documents/{id}/issues           -> ListEnvelope<QuotationIssue>
 *   POST   /projects/{projectId}/quotation-documents/{id}/sign             -> QuotationSignature (201)
 *   POST   /projects/{projectId}/quotation-documents/{id}/issues/{issueId}/sign-link
 *                                                                         -> QuotationSignLink
 *   GET    /projects/{projectId}/quotation-documents/{id}/issues/{issueId}/pdf -> application/pdf
 *
 * Money arrives as a decimal STRING, never a JS number: `1805907.02` parsed as a float and added
 * back up is how a quotation ends up disagreeing with its own PDF by a cent. Format it, do not
 * arithmetic it - the backend already excluded rate-only lines from every total it sends.
 */

const BASE = '/api/v1/project-sales';

export type QuotationScope = {
  id: string;
  scope_label: string;
  sort_order: number;
  outcome: string;
  current_version_id: string | null;
  current_version_no: number | null;
  line_count: number;
  scope_total: string;
};

/** One stored signature, the shape `quotation_signatures` serializes on every signing route. */
export type QuotationSignatureRecord = {
  id: string;
  signer_name: string | null;
  mode: string;
  image_data_uri: string | null;
  signed_at: string | null;
  ip_address: string | null;
  /** Decimal strings, or null when the browser refused. Shown as `-`, never guessed. */
  gps_lat: string | null;
  gps_lng: string | null;
};

export type QuotationDocument = {
  id: string;
  project_id: string;
  document_no: string;
  /** The number plus the revision the customer holds, e.g. "SRT/Q/2026/0141 (R2)". */
  our_ref: string | null;
  your_ref: string | null;
  doc_date: string | null;
  recipient_party_id: string | null;
  recipient_name_snapshot: string | null;
  recipient_address_snapshot: string | null;
  recipient_phone_snapshot: string | null;
  attn_name: string | null;
  subject_title: string | null;
  cover_letter_html: string | null;
  terms_html: string | null;
  signatory_name: string | null;
  signatory_phone: string | null;
  scopes: QuotationScope[];
  grand_total: string;
  issue_count: number;
  current_issue_no: number | null;
  is_issued: boolean;
  created_at: string | null;
  updated_at: string | null;
  /**
   * The signature held on the DRAFT, which is what makes the document issuable (AC-H1).
   *
   * OPTIONAL because the document GET does not serialize it yet: `serialize_document` returns no
   * signature, so on a fresh page load a signed draft is indistinguishable from an unsigned one.
   * The POST /sign response writes it into the cached document (see `useQuotationDocumentMutations`)
   * so the screen is right for the whole session in which somebody signs, and the day the backend
   * adds `signatory_signature` to the serializer this field starts arriving for free with no other
   * change. Until then a reloaded signed draft asks to be signed again, which the backend accepts
   * (re-signing a draft replaces the draft signature and never touches an issued copy).
   */
  signatory_signature?: QuotationSignatureRecord | null;
};

export type QuotationIssue = {
  id: string;
  document_id: string;
  issue_no: number;
  our_ref_text: string | null;
  issued_at: string | null;
  issued_by: string | null;
  issued_by_name: string | null;
  grand_total: string;
  scope_count: number;
};

export type QuotationDocumentBody = Partial<{
  your_ref: string | null;
  doc_date: string | null;
  attn_name: string | null;
  subject_title: string | null;
  cover_letter_html: string | null;
  terms_html: string | null;
  signatory_name: string | null;
  signatory_phone: string | null;
}>;

type Envelope<T> = { data: T[]; pagination: { total: number }; empty: boolean };

export async function listQuotationDocuments(
  projectId: string,
): Promise<QuotationDocument[]> {
  const response = await apiFetch(`${BASE}/projects/${projectId}/quotation-documents`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load quotations'));
  const body: Envelope<QuotationDocument> = await response.json();
  return body.data ?? [];
}

export async function getQuotationDocument(
  projectId: string,
  documentId: string,
): Promise<QuotationDocument> {
  const response = await apiFetch(
    `${BASE}/projects/${projectId}/quotation-documents/${documentId}`,
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load this quotation'));
  return response.json();
}

export async function createQuotationDocument(
  projectId: string,
  body: QuotationDocumentBody = {},
): Promise<QuotationDocument> {
  const response = await apiFetch(`${BASE}/projects/${projectId}/quotation-documents`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to create the quotation'));
  return response.json();
}

export async function updateQuotationDocument(
  projectId: string,
  documentId: string,
  body: QuotationDocumentBody,
): Promise<QuotationDocument> {
  const response = await apiFetch(
    `${BASE}/projects/${projectId}/quotation-documents/${documentId}`,
    { method: 'PATCH', body: JSON.stringify(body) },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to save the quotation'));
  return response.json();
}

export async function deleteQuotationDocument(
  projectId: string,
  documentId: string,
): Promise<void> {
  const response = await apiFetch(
    `${BASE}/projects/${projectId}/quotation-documents/${documentId}`,
    { method: 'DELETE' },
  );
  // 422 once issued, and the server's message names withdrawal as the way out, so it is
  // surfaced rather than replaced with a generic failure.
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to delete the quotation'));
}

export async function addQuotationScope(
  projectId: string,
  documentId: string,
  body: { scope_label: string; series_id?: string | null; notes?: string | null },
): Promise<QuotationScope> {
  const response = await apiFetch(
    `${BASE}/projects/${projectId}/quotation-documents/${documentId}/scopes`,
    { method: 'POST', body: JSON.stringify(body) },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to add the scope'));
  return response.json();
}

export async function updateQuotationScope(
  projectId: string,
  documentId: string,
  scopeId: string,
  body: Partial<{ scope_label: string; sort_order: number; notes: string | null }>,
): Promise<QuotationScope> {
  const response = await apiFetch(
    `${BASE}/projects/${projectId}/quotation-documents/${documentId}/scopes/${scopeId}`,
    { method: 'PATCH', body: JSON.stringify(body) },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to save the scope'));
  return response.json();
}

export async function issueQuotationDocument(
  projectId: string,
  documentId: string,
): Promise<QuotationIssue> {
  const response = await apiFetch(
    `${BASE}/projects/${projectId}/quotation-documents/${documentId}/issue`,
    { method: 'POST' },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to issue this quotation'));
  return response.json();
}

export async function listQuotationIssues(
  projectId: string,
  documentId: string,
): Promise<QuotationIssue[]> {
  const response = await apiFetch(
    `${BASE}/projects/${projectId}/quotation-documents/${documentId}/issues`,
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the revisions'));
  const body: Envelope<QuotationIssue> = await response.json();
  return body.data ?? [];
}

/**
 * Sign the DRAFT. Separate from issuing on purpose: a person signs, reads the document, then
 * issues. `signer_name` may be omitted, in which case the backend falls back to the document's
 * signatory. IP and user agent are stamped server-side - the browser must not source its own
 * provenance.
 */
export type QuotationSignatureBody = {
  signer_name?: string | null;
  mode: string;
  image_data_uri: string;
  /** Strings, not numbers: the column is NUMERIC(10,7) and a float round-trip can move it. */
  gps_lat?: string | null;
  gps_lng?: string | null;
};

export async function signQuotationDocument(
  projectId: string,
  documentId: string,
  body: QuotationSignatureBody,
): Promise<QuotationSignatureRecord> {
  const response = await apiFetch(
    `${BASE}/projects/${projectId}/quotation-documents/${documentId}/sign`,
    { method: 'POST', body: JSON.stringify(body) },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to save the signature'));
  return response.json();
}

export type QuotationSignLink = {
  token: string;
  /** Relative on purpose: the origin belongs to whoever is sending the link. */
  path: string;
  expires_at: string | null;
};

export async function createQuotationSignLink(
  projectId: string,
  documentId: string,
  issueId: string,
): Promise<QuotationSignLink> {
  const response = await apiFetch(
    `${BASE}/projects/${projectId}/quotation-documents/${documentId}/issues/${issueId}/sign-link`,
    { method: 'POST' },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to create the counter-sign link'));
  return response.json();
}

/**
 * The issued quotation as the customer received it, rendered from the issue snapshot.
 *
 * A 503 here is an operational fact (the host is missing the native rendering libraries) and the
 * server says so in words, which is why the message is surfaced rather than replaced.
 */
export async function downloadQuotationIssuePdf(
  projectId: string,
  documentId: string,
  issueId: string,
): Promise<Blob> {
  const response = await apiFetch(
    `${BASE}/projects/${projectId}/quotation-documents/${documentId}/issues/${issueId}/pdf`,
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to generate the PDF'));
  return response.blob();
}
