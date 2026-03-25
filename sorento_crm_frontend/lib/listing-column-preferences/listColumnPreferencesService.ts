import { apiFetch } from '@/lib/api';

export type UserListColumnConfigPayload = {
  version?: number;
  columnOrder?: string[] | null;
  columnVisibility?: Record<string, boolean> | null;
  columnSizing?: Record<string, number> | null;
};

export type UserListColumnConfigResponse = {
  listing_key: string;
  config: UserListColumnConfigPayload | null;
};

const BASE = '/api/v1/list-query/column-config';

export async function getUserListColumnConfig(listingKey: string): Promise<UserListColumnConfigResponse> {
  const key = (listingKey || '').trim();
  const res = await apiFetch(`${BASE}/${encodeURIComponent(key)}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to fetch column config');
  }
  return res.json();
}

export async function upsertUserListColumnConfig(
  listingKey: string,
  payload: UserListColumnConfigPayload,
): Promise<UserListColumnConfigResponse> {
  const key = (listingKey || '').trim();
  const res = await apiFetch(`${BASE}/${encodeURIComponent(key)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to save column config');
  }
  return res.json();
}

export async function resetUserListColumnConfig(listingKey: string): Promise<void> {
  const key = (listingKey || '').trim();
  const res = await apiFetch(`${BASE}/${encodeURIComponent(key)}`, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to reset column config');
  }
}

