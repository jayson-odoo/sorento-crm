/**
 * Shared user select service for dropdowns (teams, access agents, approvers, etc.).
 * See docs/ADR-PRODUCT-STANDARDS.md.
 */

import { apiFetch } from '@/lib/api';

export interface UserSelectItem {
  id: string;
  name: string | null;
  email: string;
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
}): Promise<UserSelectItem[]> {
  const sp = new URLSearchParams();
  if (params?.query) sp.set('query', params.query);
  if (params?.respond_synced) sp.set('respond_synced', params.respond_synced);
  if (params?.status) sp.set('status', params.status);
  if (params?.company_id) sp.set('company_id', params.company_id);
  const url = USERS_SELECT + (sp.toString() ? `?${sp.toString()}` : '');
  const response = await apiFetch(url);
  if (!response.ok) throw new Error('Failed to fetch users');
  return response.json();
}
