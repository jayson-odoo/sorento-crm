/**
 * Set-apart customers - feature service.
 *
 * Layering: components -> hooks (useSetApart) -> THIS service -> lib/api.
 *
 * Backend contract (module `sales`, mounted at /api/v1/sales):
 *   GET    /sales/set-apart-customers?query&sort&dir&page&limit   sales.reports.view
 *            sort: debtor_code | customer_name | from_month | to_month
 *            -> { data: SetApartRow[], pagination }
 *   GET    /sales/set-apart-customers/customer-options?query      sales.set_apart.edit
 *            -> { data: [{ value, label }] }
 *   POST   /sales/set-apart-customers   body { customer_id, from_month, to_month|null }
 *   PATCH  /sales/set-apart-customers/{id}
 *   DELETE /sales/set-apart-customers/{id}
 * 422 codes: set_apart_overlap, set_apart_months_inverted, invalid_month.
 * The screens delete through the parked action `sales_set_apart.delete` (D7).
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type {
  SetApartCustomerOption,
  SetApartListParams,
  SetApartListResponse,
  SetApartRow,
  SetApartSavePayload,
} from '../types/setApart.types';

const BASE = '/api/v1/sales/set-apart-customers';

async function read<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) throw new Error(await extractApiError(response, fallback));
  return response.json();
}

function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
}

export async function getSetApartCustomers(params: SetApartListParams): Promise<SetApartListResponse> {
  const usp = buildDataGridParams(params);
  return read(await apiFetch(`${BASE}?${usp.toString()}`), 'Failed to load set-apart customers');
}

export async function getSetApartCustomerOptions(query: string): Promise<SetApartCustomerOption[]> {
  const q = query.trim();
  const url = q ? `${BASE}/customer-options?${new URLSearchParams({ query: q }).toString()}` : `${BASE}/customer-options`;
  const body = await read<{ data: SetApartCustomerOption[] }>(await apiFetch(url), 'Failed to load customers');
  return body.data;
}

export async function createSetApart(payload: SetApartSavePayload): Promise<SetApartRow> {
  return read(await apiFetch(BASE, jsonInit('POST', payload)), 'Failed to add the customer');
}

export async function updateSetApart(id: string, payload: SetApartSavePayload): Promise<SetApartRow> {
  return read(await apiFetch(`${BASE}/${id}`, jsonInit('PATCH', payload)), 'Failed to save the customer');
}
