import { apiFetch } from '@/lib/api';
import type { ImportLog } from '../types/importLog.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getImportLogs(
  params: DataGridApiFetchParams & { entity_type?: string },
): Promise<DataGridApiResponse<ImportLog>> {
  const { pageIndex, pageSize, entity_type } = params;
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(entity_type ? { entity_type } : {}),
  });
  const response = await apiFetch(`/api/v1/system/import-logs?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch import logs');
  return response.json();
}

export async function getImportLog(logId: string): Promise<ImportLog> {
  const response = await apiFetch(`/api/v1/system/import-logs/${logId}`);
  if (!response.ok) throw new Error('Failed to fetch import log');
  return response.json();
}
