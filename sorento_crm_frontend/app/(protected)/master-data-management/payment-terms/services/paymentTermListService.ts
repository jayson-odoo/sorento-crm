/**
 * Payment terms (read-only list) - feature service.
 *
 * Layering: hooks (usePaymentTermList) -> THIS service -> lib/api -> backend
 * `GET /api/v1/master-data/payment-terms/?page&limit&query&sort&dir` -> DataGridApiResponse;
 * sort keys term_code | term_rule | company_code | is_active. Requires
 * `master_data.payment_terms.view`. AutoCount owns the rows (ESB sync), so there is no write.
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export interface PaymentTermRow {
  id: string;
  /** AutoCount DisplayTerm: what prints on a quotation. */
  term_code: string;
  /** AutoCount Terms: the calculation rule. */
  term_rule: string | null;
  /** The company (AutoCount book) the term belongs to. */
  company_code: string;
  is_active: boolean;
  updated_at: string | null;
}

const BASE = '/api/v1/master-data/payment-terms';

export async function getPaymentTermList(
  params: DataGridApiFetchParams,
): Promise<DataGridApiResponse<PaymentTermRow>> {
  const queryParams = buildDataGridParams(params);
  const response = await apiFetch(`${BASE}/?${queryParams.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to fetch payment terms'));
  }
  return (await response.json()) as DataGridApiResponse<PaymentTermRow>;
}
