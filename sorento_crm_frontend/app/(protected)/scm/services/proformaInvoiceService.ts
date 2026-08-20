/**
 * ============================================================================
 * SCM proforma invoices - the supplier's priced document, held and read
 * ============================================================================
 * Layering: ProformaInvoicesView / ProformaUploadDialog / ProformaInvoiceDetail
 * -> THIS service -> lib/api-client -> backend.
 *
 * ── BACKEND CONTRACT (app/api/v1/scm/proforma_invoices.py) ─────────────────
 *
 *  POST /api/v1/scm/proforma-invoices/preview  -> 200 ProformaInvoicePreview
 *       multipart: file (required) + supplier_id (required) [+ currency]
 *  POST /api/v1/scm/proforma-invoices/apply    -> 200 ProformaApplyResult
 *       ?validate_only=true                    -> 200 UploadTestResult
 *       multipart: file + supplier_id [+ currency]
 *  GET  /api/v1/scm/proforma-invoices?supplier_id&limit&offset -> 200 ProformaInvoiceListResponse
 *       Fixed `created_at DESC` sort, NO page/sort/query params - offset paging only.
 *  GET  /api/v1/scm/proforma-invoices/{id}     -> 200 ProformaInvoiceDetail
 *  DELETE /api/v1/scm/proforma-invoices/{id}   -> 204, hard delete
 *
 * The supplier travels WITH the file because the document never says reliably who wrote
 * it. Currency does NOT have to: the document usually states it and the supplier's price
 * list often does, so the form field is the last resort (AC-P3.1) - append it only when the
 * operator actually typed one, never an empty string.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { UploadTestResult } from '../reorder/components/UploadTestVerdict';

/** Where a document's currency came from, in the order AC-P3.1 resolves it. */
export type CurrencySource = 'form' | 'document' | 'supplier_price_list' | 'none';

export interface ProformaDocumentSummary {
  index: number;
  pi_number: string;
  /** False when the number is derived (`PI-<file stem>-<block>`), never stated by the file. */
  pi_number_stated: boolean;
  invoice_date: string | null;
  container_no: string | null;
  bl_no: string | null;
  lines: number;
  qty: number | null;
  total: number | null;
  /** The document's own printed total, when it has one - to compare against `total`. */
  stated_total: number | null;
  unmatched_items: string[];
  currency: string | null;
  currency_source: CurrencySource;
}

export interface ProformaInvoicePreview {
  /** Named `ok` to satisfy the shared two-step upload hook. */
  ok: boolean;
  missing_columns: string[];
  problems: string[];
  supplier_id: string;
  supplier_code: string | null;
  supplier_name: string | null;
  documents: ProformaDocumentSummary[];
  document_count: number;
  line_count: number;
  priced_lines: number;
  rows_read: number;
  unmatched_item_codes: string[];
  unmatched_items: number;
  unmapped_headers: string[];
  currency: string | null;
  currency_source: CurrencySource;
  priced_lines_without_currency: number;
}

export interface ProformaApplyResultDocument {
  index: number;
  invoice_id: string;
  pi_number: string;
  invoice_date: string | null;
  currency: string | null;
  currency_source: CurrencySource;
  lines: number;
  total_amount: number | null;
  unmatched_items: string[];
  created: boolean;
}

export interface ProformaApplyResult {
  documents_created: number;
  documents_updated: number;
  results: ProformaApplyResultDocument[];
  summary: Record<string, unknown>;
}

export interface ProformaInvoiceListRow {
  id: string;
  supplier_id: string;
  supplier_code: string | null;
  supplier_name: string | null;
  pi_number: string;
  invoice_date: string | null;
  currency: string | null;
  container_no: string | null;
  bl_no: string | null;
  total_amount: number | null;
  line_count: number;
  source_ref: string | null;
  block_index: number | null;
  uploaded_by: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ProformaInvoiceListResponse {
  data: ProformaInvoiceListRow[];
  total: number;
  limit: number;
  offset: number;
}

export interface ProformaInvoiceLine {
  id: string;
  line_no: number;
  row_number: number | null;
  item_code: string;
  description: string | null;
  qty: number | null;
  uom: string | null;
  unit_price: number | null;
  amount: number | null;
  po_ref: string | null;
  remark: string | null;
  /** The product we hold, by CODE - null when the line matched nothing (AC-P1.3). */
  product_code: string | null;
  matched: boolean;
}

export interface ProformaInvoiceDetail extends ProformaInvoiceListRow {
  lines: ProformaInvoiceLine[];
}

async function readJson<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) throw new Error(await extractApiError(res, fallback));
  return (await res.json()) as T;
}

function proformaForm(file: File, supplierId: string, currency?: string | null): FormData {
  const body = new FormData();
  body.append('file', file);
  body.append('supplier_id', supplierId);
  // Only when the operator typed one: an empty string would be read as a currency the
  // backend cannot resolve and refuse a file the document itself could have answered.
  if (currency) body.append('currency', currency);
  return body;
}

export async function previewProformaInvoice(
  file: File,
  supplierId: string,
  currency?: string | null,
): Promise<ProformaInvoicePreview> {
  const res = await apiFetch('/api/v1/scm/proforma-invoices/preview', {
    method: 'POST',
    body: proformaForm(file, supplierId, currency),
  });
  return readJson<ProformaInvoicePreview>(res, 'Failed to read the proforma invoice');
}

export async function applyProformaInvoice(
  file: File,
  supplierId: string,
  currency?: string | null,
): Promise<ProformaApplyResult> {
  const res = await apiFetch('/api/v1/scm/proforma-invoices/apply', {
    method: 'POST',
    body: proformaForm(file, supplierId, currency),
  });
  return readJson<ProformaApplyResult>(res, 'Failed to save the proforma invoice');
}

export async function testProformaInvoice(
  file: File,
  supplierId: string,
  currency?: string | null,
): Promise<UploadTestResult> {
  const res = await apiFetch('/api/v1/scm/proforma-invoices/apply?validate_only=true', {
    method: 'POST',
    body: proformaForm(file, supplierId, currency),
  });
  return readJson<UploadTestResult>(res, 'Failed to test the proforma invoice');
}

export interface ListProformaInvoicesOptions {
  supplierId?: string | null;
  limit?: number;
  offset?: number;
}

export async function listProformaInvoices(
  opts: ListProformaInvoicesOptions = {},
): Promise<ProformaInvoiceListResponse> {
  const params = new URLSearchParams();
  if (opts.supplierId) params.set('supplier_id', opts.supplierId);
  params.set('limit', String(opts.limit ?? 25));
  params.set('offset', String(opts.offset ?? 0));
  const res = await apiFetch(`/api/v1/scm/proforma-invoices?${params.toString()}`);
  return readJson<ProformaInvoiceListResponse>(res, 'Failed to load proforma invoices');
}

export async function getProformaInvoice(id: string): Promise<ProformaInvoiceDetail> {
  const res = await apiFetch(`/api/v1/scm/proforma-invoices/${id}`);
  return readJson<ProformaInvoiceDetail>(res, 'Failed to load the proforma invoice');
}

export async function deleteProformaInvoice(id: string): Promise<void> {
  const res = await apiFetch(`/api/v1/scm/proforma-invoices/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to delete the proforma invoice'));
}
