/**
 * Chatbot stock ask v2 S5: the customer's stock asks on the CRM (Asks tab).
 * The portal's Customer asks page reads the same rows through the portal client
 * (`app/(auth)/portal/lib/customer-asks-service.ts`).
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { StockAsk, StockAskPage, StockAskPatch } from '@/lib/stock-asks';

const BASE = '/api/v1/order-management/customers';

export async function listCustomerAsks(
  customerId: string,
  params: { pageIndex: number; pageSize: number },
): Promise<StockAskPage> {
  const qs = buildDataGridParams({ pageIndex: params.pageIndex, pageSize: params.pageSize });
  const response = await apiFetch(`${BASE}/${customerId}/asks?${qs.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load stock asks'));
  return response.json();
}

export async function updateCustomerAsk(
  customerId: string,
  askId: string,
  patch: StockAskPatch,
): Promise<StockAsk> {
  const response = await apiFetch(`${BASE}/${customerId}/asks/${askId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to update the ask'));
  return response.json();
}
