/**
 * Countries - feature service.
 *
 * Layering: hooks (useCountries) -> THIS service -> lib/api -> backend
 * `/api/v1/master-data/countries`.
 *
 * -- PHASE-2 BACKEND CONTRACT (not yet built, `PLAN-local-supplier-oi-routing.md` S1) --------
 *
 *   GET    /master-data/countries              ?page&limit&query&sort&dir
 *          -> DataGridApiResponse<Country>, same shape as every other DataGrid listing
 *             (`{ data, empty, pagination: { total, page } }`); `query` matches code or name.
 *          Requires `master_data.countries.view`.
 *   GET    /master-data/countries/select        -> CountrySelectItem[] (active rows only)
 *          Requires `master_data.countries.view`.
 *   GET    /master-data/countries/{id}          -> Country
 *   POST   /master-data/countries               body CountryFormData -> Country
 *          409 on a duplicate code, case-insensitive. Requires `.add`.
 *   PUT    /master-data/countries/{id}          body Partial<CountryFormData> -> Country
 *          409 on a duplicate code. Requires `.edit`.
 *   DELETE /master-data/countries/{id}          -> void
 *          409, naming the count of referencing suppliers, when any supplier still points at
 *          it. Requires `.delete`. Wired through the deferred record-action registry as
 *          `country.delete` (see `hooks/useDeferredRowAction`), same hard-delete window every
 *          other reference table uses.
 *
 * Seeded with the full ISO 3166-1 alpha-2 list by migration `499_countries`; `MY` is
 * `Malaysia`. A deviation from this shape updates this header and both sides in the same
 * change.
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type { Country, CountryFormData, CountrySelectItem } from '../types/country.types';

const BASE = '/api/v1/master-data/countries';

export async function getCountries(
  params: DataGridApiFetchParams,
): Promise<DataGridApiResponse<Country>> {
  const queryParams = buildDataGridParams(params);
  const response = await apiFetch(`${BASE}?${queryParams.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to fetch countries'));
  return (await response.json()) as DataGridApiResponse<Country>;
}

export async function getCountrySelect(): Promise<CountrySelectItem[]> {
  const response = await apiFetch(`${BASE}/select`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to fetch countries'));
  return (await response.json()) as CountrySelectItem[];
}

export async function getCountry(id: string): Promise<Country> {
  const response = await apiFetch(`${BASE}/${id}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to fetch country'));
  return (await response.json()) as Country;
}

export async function createCountry(data: CountryFormData): Promise<Country> {
  const response = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to create country'));
  return (await response.json()) as Country;
}

export async function updateCountry(
  id: string,
  data: Partial<CountryFormData>,
): Promise<Country> {
  const response = await apiFetch(`${BASE}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to update country'));
  return (await response.json()) as Country;
}

export async function deleteCountry(id: string): Promise<void> {
  const response = await apiFetch(`${BASE}/${id}`, { method: 'DELETE' });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to delete country'));
}
