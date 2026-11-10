/**
 * The Costing party picker's search: customers by name or code from the staff customer select
 * (`/order-management/customers/select`), in the shape `CustomerDebtorCombobox` takes. Kept apart
 * from `costingService` because it reads another module's route.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { DebtorLookupItem } from '@/app/(auth)/portal/lib/portal-client';

export async function lookupCostingParties(query: string): Promise<DebtorLookupItem[]> {
  const search = new URLSearchParams({ limit: '20', offset: '0' });
  if (query.trim()) search.set('query', query.trim());
  const response = await apiFetch(`/api/v1/order-management/customers/select?${search.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not load customers'));
  const body = (await response.json()) as {
    data?: { id: string; customer_code: string; customer_name: string }[];
  };
  return (body.data ?? []).map((row) => ({
    customer_id: row.id,
    debtor_name: row.customer_name,
    customer_code: row.customer_code,
    sales_type: null,
  }));
}
