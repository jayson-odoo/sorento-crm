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
