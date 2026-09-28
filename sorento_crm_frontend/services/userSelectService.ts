/**
 * Shared user select service for dropdowns (teams, access agents, approvers, etc.).
 * See docs/ADR-PRODUCT-STANDARDS.md.
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export interface UserSelectItem {
  id: string;
  name: string | null;
  /** Null for a phone-only user (identity S0/S3: email is optional). */
  email: string | null;
  respond_user_id?: string | null;
  respond_synced?: string | null;
}

const USERS_SELECT = '/api/user-management/users/select';

export async function getUsersSelect(params?: {
  query?: string;
  respond_synced?: string;
  status?: string;
  /** Only users granted this company. Team membership requires the grant. */
  company_id?: string;
  /** The user holding this phone (identity S3, "Link this contact to <name> instead"). */
  phone?: string;
  /** The user linked to this WhatsApp contact (identity S3, "Open user"). */
  respond_contact_id?: string;
  /** Only users with no linked WhatsApp contact (identity S3, "Link existing user"). */
  unlinked?: boolean;
}): Promise<UserSelectItem[]> {
  const sp = new URLSearchParams();
  if (params?.query) sp.set('query', params.query);
  if (params?.respond_synced) sp.set('respond_synced', params.respond_synced);
  if (params?.status) sp.set('status', params.status);
  if (params?.company_id) sp.set('company_id', params.company_id);
  if (params?.phone) sp.set('phone', params.phone);
  if (params?.respond_contact_id) sp.set('respond_contact_id', params.respond_contact_id);
  if (params?.unlinked) sp.set('unlinked', 'true');
  const url = USERS_SELECT + (sp.toString() ? `?${sp.toString()}` : '');
  const response = await apiFetch(url);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to fetch users'));
  return response.json();
}
