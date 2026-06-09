import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type { RespondOutboxRow } from '../types/respondOutbox.types';

export async function getRespondOutbox(
  params: DataGridApiFetchParams & {
    status?: string;
    business_table?: string;
    query?: string;
  },
): Promise<DataGridApiResponse<RespondOutboxRow>> {
  const { pageIndex, pageSize, status, business_table, query } = params;
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(status ? { status } : {}),
    ...(business_table ? { business_table } : {}),
    ...(query ? { query } : {}),
  });
  const response = await apiFetch(
    `/api/v1/system/respond-outbox?${queryParams.toString()}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to fetch Respond outbox'));
  }
  return response.json();
}
