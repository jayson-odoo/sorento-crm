import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { TaxCode, MirrorAnnotationPayload } from '../types/taxCode.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

const BASE = '/api/v1/master-data/tax-codes';

export async function getTaxCodes(
  params: DataGridApiFetchParams,
): Promise<DataGridApiResponse<TaxCode>> {
  const { pageIndex, pageSize, sorting, searchQuery } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
  });
  const response = await apiFetch(`${BASE}?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch tax codes');
  return response.json();
}

export async function getTaxCode(id: string): Promise<TaxCode> {
  const response = await apiFetch(`${BASE}/${id}`);
  if (!response.ok) throw new Error('Failed to fetch tax code');
  return response.json();
}

export async function annotateTaxCode(
  id: string,
  data: MirrorAnnotationPayload,
): Promise<TaxCode> {
  const response = await apiFetch(`${BASE}/${id}/annotation`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save note'));
  }
  return response.json();
}
