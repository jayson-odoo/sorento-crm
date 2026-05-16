import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type { EmailOutboxRow } from '../types/emailOutbox.types';

export async function getEmailOutbox(
  params: DataGridApiFetchParams & { status?: string; event_key?: string; query?: string },
): Promise<DataGridApiResponse<EmailOutboxRow>> {
  const { pageIndex, pageSize, status, event_key, query } = params;
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(status ? { status } : {}),
    ...(event_key ? { event_key } : {}),
    ...(query ? { query } : {}),
  });
  const response = await apiFetch(`/api/v1/system/email-outbox?${queryParams.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to fetch email outbox'));
  return response.json();
}

export async function getEmailOutboxRow(id: string): Promise<EmailOutboxRow> {
  const response = await apiFetch(`/api/v1/system/email-outbox/${id}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to fetch outbox row'));
  return response.json();
}

export async function retryEmailOutboxRow(id: string): Promise<EmailOutboxRow> {
  const response = await apiFetch(`/api/v1/system/email-outbox/${id}/retry`, { method: 'POST' });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to retry outbox row'));
  return response.json();
}

export async function cancelEmailOutboxRow(id: string): Promise<EmailOutboxRow> {
  const response = await apiFetch(`/api/v1/system/email-outbox/${id}/cancel`, { method: 'POST' });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to cancel outbox row'));
  return response.json();
}
