import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError, type DataGridParamsInput } from '@/lib/api-client';
import type { RespondContact } from '../../types/contact.types';

/**
 * Contact record reads used by the contact detail shell.
 *
 * GET /api/v1/user-management/contacts/{id}           -> RespondContact
 * GET /api/v1/user-management/contacts?page&limit&... -> { data: RespondContact[], pagination }
 */

export interface RespondContactListResponse {
  data: RespondContact[];
  pagination?: { total: number };
}

export async function getContact(contactId: string): Promise<RespondContact> {
  const response = await apiFetch(`/api/user-management/contacts/${contactId}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load contact'));
  }
  return (await response.json()) as RespondContact;
}

export async function getContacts(
  params: DataGridParamsInput,
): Promise<RespondContactListResponse> {
  const query = buildDataGridParams(params);
  const response = await apiFetch(`/api/user-management/contacts?${query.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load contacts'));
  }
  return (await response.json()) as RespondContactListResponse;
}
