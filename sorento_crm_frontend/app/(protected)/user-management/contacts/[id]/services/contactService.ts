import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError, type DataGridParamsInput } from '@/lib/api-client';
import type { RespondContact } from '../../types/contact.types';

/**
 * Contact record reads used by the contact detail shell.
 *
 * GET /api/v1/user-management/contacts/{id}           -> RespondContact
 * GET /api/v1/user-management/contacts?page&limit&... -> { data: RespondContact[], pagination }
 * GET /api/v1/user-management/contacts/{id}/companies -> { id, name }[]
 */

// PHASE 1 MOCK: swap in Phase 2 once the backend answers the S3 contract's 1.7
// fields (`is_salesperson`, `suggested_role_slug`, `linked_user*`) on these two
// routes. Until then every contact reads as unlinked, suggesting `portal_user` -
// the honest default, since nothing is actually linked yet.
const S3_USE_MOCKS = true;

function withS3ContactMocks(contact: RespondContact): RespondContact {
  if (!S3_USE_MOCKS) return contact;
  return {
    is_salesperson: false,
    suggested_role_slug: 'portal_user',
    linked_user_id: null,
    linked_user_name: null,
    linked_user: null,
    ...contact,
  };
}

export interface RespondContactListResponse {
  data: RespondContact[];
  pagination?: { total: number };
}

export async function getContact(contactId: string): Promise<RespondContact> {
  const response = await apiFetch(`/api/user-management/contacts/${contactId}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load contact'));
  }
  return withS3ContactMocks((await response.json()) as RespondContact);
}

export async function getContacts(
  params: DataGridParamsInput,
): Promise<RespondContactListResponse> {
  const query = buildDataGridParams(params);
  const response = await apiFetch(`/api/user-management/contacts?${query.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load contacts'));
  }
  const page = (await response.json()) as RespondContactListResponse;
  return { ...page, data: (page.data ?? []).map(withS3ContactMocks) };
}

/** Superadmin-only; a 403 for anyone else resolves to an empty list rather than
 *  an error, since the caller only uses this to prefill a form. */
export async function getContactCompanies(
  contactId: string,
): Promise<{ id: string; name: string }[]> {
  const response = await apiFetch(`/api/user-management/contacts/${contactId}/companies`);
  if (!response.ok) return [];
  return (await response.json()) as { id: string; name: string }[];
}
