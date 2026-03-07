import { apiFetch } from '@/lib/api';

const ME_PERMISSIONS_URL = '/api/user-management/users/me/permissions';

export interface MyPermissionsResponse {
  permissions: string[];
}

export async function fetchMyPermissions(): Promise<string[]> {
  const response = await apiFetch(ME_PERMISSIONS_URL);
  if (!response.ok) {
    throw new Error('Failed to fetch permissions');
  }
  const data = (await response.json()) as MyPermissionsResponse;
  return data.permissions ?? [];
}
