import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { SalesAgent, MirrorAnnotationPayload } from '../types/salesAgent.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

const BASE = '/api/v1/master-data/sales-agents';

export async function getSalesAgents(
  params: DataGridApiFetchParams,
): Promise<DataGridApiResponse<SalesAgent>> {
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
  if (!response.ok) throw new Error('Failed to fetch sales agents');
  return response.json();
}

export async function getSalesAgent(id: string): Promise<SalesAgent> {
  const response = await apiFetch(`${BASE}/${id}`);
  if (!response.ok) throw new Error('Failed to fetch sales agent');
  return response.json();
}

export async function annotateSalesAgent(
  id: string,
  data: MirrorAnnotationPayload,
): Promise<SalesAgent> {
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
