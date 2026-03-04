import { apiFetch } from '@/lib/api';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type { OutgoingMail } from '../types/outgoingMail.types';

export async function getOutgoingMails(
  params: DataGridApiFetchParams & { status?: string; query?: string },
): Promise<DataGridApiResponse<OutgoingMail>> {
  const { pageIndex, pageSize, status, query } = params;
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(status ? { status } : {}),
    ...(query ? { query } : {}),
  });
  const response = await apiFetch(`/api/v1/system/outgoing-mails?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch outgoing mails');
  return response.json();
}

