import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

const BASE = '/api/v1/notifications/coverage';

/** A coverage subscription: I (the subscriber) cover for target_user. */
export interface CoverageSub {
  id: string;
  target_user_id: string;
  target_user_name: string;
  is_active: boolean;
  expires_at: string | null;
  created_at: string;
}

export interface CoverageSubCreateResult {
  id: string;
  target_user_id: string;
  is_active: boolean;
  expires_at: string | null;
}

/** List the colleagues I'm covering for. */
export async function getMyCoverage(): Promise<CoverageSub[]> {
  const response = await apiFetch(`${BASE}/`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load coverage'));
  }
  const body = await response.json();
  return Array.isArray(body?.data) ? (body.data as CoverageSub[]) : [];
}

/** Subscribe to a colleague's SLA assignments/escalations, optionally with an end date. */
export async function subscribeCoverage(
  targetUserId: string,
  expiresAt?: string,
): Promise<CoverageSubCreateResult> {
  const response = await apiFetch(`${BASE}/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      target_user_id: targetUserId,
      ...(expiresAt ? { expires_at: expiresAt } : {}),
    }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to add coverage'));
  }
  return response.json();
}

/** Stop covering for a colleague. */
export async function unsubscribeCoverage(targetUserId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/${targetUserId}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to remove coverage'));
  }
}
