import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { CreditTerm, MirrorAnnotationPayload } from '../types/creditTerm.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

const BASE = '/api/v1/master-data/credit-terms';

export async function getCreditTerms(
  params: DataGridApiFetchParams,
): Promise<DataGridApiResponse<CreditTerm>> {
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
  if (!response.ok) throw new Error('Failed to fetch credit terms');
  return response.json();
}

export async function getCreditTerm(id: string): Promise<CreditTerm> {
  const response = await apiFetch(`${BASE}/${id}`);
  if (!response.ok) throw new Error('Failed to fetch credit term');
  return response.json();
}

export async function annotateCreditTerm(
  id: string,
  data: MirrorAnnotationPayload,
): Promise<CreditTerm> {
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
