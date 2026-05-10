/**
 * Admin impersonation: start, stop, and read the current session.
 * The backend mirrors the active session in the `impersonation_sessions` table;
 * this service exposes the three CRUD-shaped endpoints.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { ImpersonationSession } from '@/lib/impersonation-store';

const BASE = '/api/user-management/impersonation';

type ApiSessionResponse = {
  session_id: string;
  started_at: string;
  target_user: {
    id: string;
    name: string | null;
    email: string | null;
    avatar: string | null;
    role_name: string | null;
  };
};

function _adapt(api: ApiSessionResponse): ImpersonationSession {
  return {
    sessionId: api.session_id,
    startedAt: api.started_at,
    targetUser: api.target_user,
  };
}

export async function startImpersonation(targetUserId: string): Promise<ImpersonationSession> {
  const response = await apiFetch(`${BASE}/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_user_id: targetUserId }),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to start impersonation'));
  return _adapt(await response.json());
}

export async function stopImpersonation(): Promise<void> {
  const response = await apiFetch(`${BASE}/stop`, { method: 'POST' });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to stop impersonation'));
}

export async function fetchCurrentImpersonation(): Promise<ImpersonationSession | null> {
  const response = await apiFetch(`${BASE}/current`);
  if (!response.ok) {
    // Treat any failure as "no active session" — banner just hides.
    return null;
  }
  const body = (await response.json()) as ApiSessionResponse | null;
  return body ? _adapt(body) : null;
}
