/**
 * sessionService - the signed-in user's active staff sessions ("your devices").
 *
 * Backend contract (FastAPI-owned rolling sessions):
 *   GET    /api/v1/auth/sessions                 -> SessionInfo[]
 *   DELETE /api/v1/auth/sessions/{id}            -> { message }
 *   POST   /api/v1/auth/sessions/revoke-others   -> { message, count }
 *   POST   /api/v1/user-management/users/{id}/force-logout -> { message, count } (admin)
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export interface SessionInfo {
  id: string;
  device_label: string;
  ip_address?: string | null;
  last_seen_at?: string | null;
  created_at?: string | null;
  current: boolean;
}

export async function fetchSessions(): Promise<SessionInfo[]> {
  const res = await apiFetch('/api/v1/auth/sessions');
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load sessions'));
  return (await res.json()) as SessionInfo[];
}

export async function revokeSession(id: string): Promise<void> {
  const res = await apiFetch(`/api/v1/auth/sessions/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to sign out device'));
}

export async function revokeOtherSessions(): Promise<{ count: number }> {
  const res = await apiFetch('/api/v1/auth/sessions/revoke-others', { method: 'POST' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to sign out other devices'));
  return res.json();
}

/** Admin: force-logout another user from every device. */
export async function forceLogoutUser(userId: string): Promise<{ count: number }> {
  const res = await apiFetch(`/api/v1/user-management/users/${userId}/force-logout`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to sign out user'));
  return res.json();
}
