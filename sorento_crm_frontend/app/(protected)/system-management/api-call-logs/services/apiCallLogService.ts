import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { ApiCallLogFilters, ApiCallLogListResponse } from '../types/apiCallLog.types';

export async function getApiCallLogs(
  filters: ApiCallLogFilters,
): Promise<ApiCallLogListResponse> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      params.set(key, String(value));
    }
  });
  const response = await apiFetch(`/api/v1/system/api-call-logs?${params.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load API call logs'));
  return response.json();
}

/**
 * Distinct sources present in the data, for the filter dropdown. Live values
 * rather than a hardcoded list so a new caller shows up without a code change.
 */
export async function getApiCallLogSources(): Promise<string[]> {
  const response = await apiFetch('/api/v1/system/api-call-logs/sources');
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load sources'));
  return response.json();
}
