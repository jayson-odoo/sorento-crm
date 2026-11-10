import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * QUOTE-TERMS-SELECT: the Payment Terms select's options, this company's active AutoCount terms
 * (synced by the ESB, never typed here).
 *
 *   GET /config/quotation-templates/payment-terms                       (terms template dialog)
 *   GET /projects/{projectId}/quotation-documents/payment-terms         (quotation form)
 */
const BASE = '/api/v1/project-sales';

export interface PaymentTermOption {
  id: string;
  code: string;
  description: string | null;
  /** What prints: the description, else the code. */
  label: string;
}

export type ValidityUnit = 'day' | 'week' | 'month' | 'year';

export const VALIDITY_UNITS: { value: ValidityUnit; label: string }[] = [
  { value: 'day', label: 'Days' },
  { value: 'week', label: 'Weeks' },
  { value: 'month', label: 'Months' },
  { value: 'year', label: 'Years' },
];

/** The picks behind the printed Payment Terms and Validity texts. */
export interface QuoteTermsPick {
  payment_term_id?: string | null;
  validity_value?: number | null;
  validity_unit?: ValidityUnit | null;
}

async function fetchTerms(url: string): Promise<PaymentTermOption[]> {
  const response = await apiFetch(url);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the payment terms'));
  const body: { data: PaymentTermOption[] } = await response.json();
  return body.data;
}

export function listTemplatePaymentTerms(): Promise<PaymentTermOption[]> {
  return fetchTerms(`${BASE}/config/quotation-templates/payment-terms`);
}

export function listQuotationPaymentTerms(projectId: string): Promise<PaymentTermOption[]> {
  return fetchTerms(`${BASE}/projects/${projectId}/quotation-documents/payment-terms`);
}

/** As the server prints it: `2 WEEKS`, `1 MONTH`. */
export function formatValidity(value: number, unit: ValidityUnit): string {
  return `${value} ${unit.toUpperCase()}${value === 1 ? '' : 'S'}`;
}
