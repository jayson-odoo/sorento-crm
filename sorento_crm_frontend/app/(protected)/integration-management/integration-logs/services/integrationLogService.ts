import { apiFetch } from '@/lib/api';
import type { IntegrationLog, IntegrationLogResponse } from '../types/integrationLog.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getIntegrationLogs(params: DataGridApiFetchParams & { 
  status?: string; 
  integration_channel?: string; 
  business_table?: string; 
  business_id?: string; 
}): Promise<DataGridApiResponse<IntegrationLog>> {
  const { pageIndex, pageSize, sorting, searchQuery, status, integration_channel, business_table, business_id } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(status ? { status } : {}),
    ...(integration_channel ? { integration_channel } : {}),
    ...(business_table ? { business_table } : {}),
    ...(business_id ? { business_id } : {}),
  });
  const response = await apiFetch(`/api/v1/integrations/logs?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch integration logs');
  return response.json();
}

export async function getIntegrationLog(id: string): Promise<IntegrationLogResponse> {
  const response = await apiFetch(`/api/v1/integrations/logs/${id}`);
  if (!response.ok) throw new Error('Failed to fetch integration log');
  return response.json();
}

export async function updateIntegrationLog(id: string, data: {
  status: string;
  status_code?: number;
  response_payload?: string;
  error_code?: string;
  error_message?: string;
}): Promise<IntegrationLogResponse> {
  const response = await apiFetch(`/api/v1/integrations/logs/${id}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update integration log' }));
    throw new Error(error.message || 'Failed to update integration log');
  }
  return response.json();
}

export async function retryIntegrationLog(id: string): Promise<IntegrationLogResponse> {
  const response = await apiFetch(`/api/v1/integrations/logs/${id}/retry`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to retry integration log' }));
    throw new Error(error.message || 'Failed to retry integration log');
  }
  return response.json();
}
