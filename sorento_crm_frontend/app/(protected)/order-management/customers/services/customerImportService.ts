import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * The customer importer's API contract (UAC-customer-importer, AC-5).
 *
 * ONE endpoint, two modes, exactly as GRN and SPO do it:
 *
 *   POST /api/v1/order-management/customers/import?validate_only=true
 *     multipart { file }
 *     200 { valid, errors[], warnings[], summary: CustomerImportSummary }
 *          Nothing is written. The read runs at the SAME company scope the real
 *          import will run at, so Test and Confirm can never disagree.
 *
 *   POST /api/v1/order-management/customers/import
 *     multipart { file }
 *     202 { message, job_id, id }
 *          A queued background job. `job_id` is the import-job id the drawer and
 *          /system-management/import-jobs/{job_id} page key on.
 *
 *   400 on either mode when the session has no single active company: customers are
 *       an owned table (ADR 0007), so "which company's book is this?" has no answer
 *       and the job is refused before it queues (AC-2.3).
 *   403 without `order_management.customers.import`.
 *
 * Both modes accept .xlsx / .xls / .xlsm. Macro workbooks are stripped server-side;
 * the ORIGINAL bytes are what gets retained for tracing (AC-5.5).
 */

export interface CustomerImportRowProblem {
  /** 1-based row number in the source sheet. */
  row: number;
  reason: string;
}

export interface CustomerImportSummary {
  /** Data rows the reader recognised (excludes title lines above the table). */
  total_rows: number;
  would_create: number;
  would_update: number;
  would_unchanged: number;
  would_skip: number;
  /**
   * Rows that would import but want a human's eye: a near-identical name already on
   * the same customer code (AC-1.6). Never a blocker.
   */
  needs_review: number;
  /** Column headings no alias could place, by name (AC-4.3). */
  unmapped_headers: string[];
  /** Required columns the file does not carry at all. */
  missing_columns: string[];
  problems: CustomerImportRowProblem[];
}

export interface CustomerImportValidateResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary?: CustomerImportSummary;
}

export interface CustomerImportQueuedResult {
  message: string;
  job_id: string;
  id: string;
}

const IMPORT_PATH = '/api/v1/order-management/customers/import';

/** Read the file and report what it would do. Writes nothing. */
export async function validateCustomerImport(
  file: File,
): Promise<CustomerImportValidateResult> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiFetch(`${IMPORT_PATH}?validate_only=true`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not read the file'));
  }
  return response.json();
}

/** Queue the import. The work is not tied to the tab. */
export async function importCustomers(file: File): Promise<CustomerImportQueuedResult> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiFetch(IMPORT_PATH, { method: 'POST', body: formData });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to queue the customer import'));
  }
  return response.json();
}
