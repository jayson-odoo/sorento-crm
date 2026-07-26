import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { TaxEntity, MirrorAnnotationPayload } from '../types/taxEntity.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

const BASE = '/api/v1/master-data/tax-entities';

export async function getTaxEntities(
  params: DataGridApiFetchParams,
): Promise<DataGridApiResponse<TaxEntity>> {
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
  if (!response.ok) throw new Error('Failed to fetch tax entities');
  return response.json();
}

export async function getTaxEntity(id: string): Promise<TaxEntity> {
  const response = await apiFetch(`${BASE}/${id}`);
  if (!response.ok) throw new Error('Failed to fetch tax entity');
  return response.json();
}

export async function annotateTaxEntity(
  id: string,
  data: MirrorAnnotationPayload,
): Promise<TaxEntity> {
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
