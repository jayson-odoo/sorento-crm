import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

const BASE = '/api/v1/notifications/coverage';

/** A coverage subscription: I (the subscriber) cover for target_user. */
export interface CoverageSub {
  id: string;
  target_user_id: string;
  target_user_name: string;
  is_active: boolean;
  /** True = their SLA tasks are auto-assigned to me; false = notify-only (I take over manually). */
  redirect_assignments: boolean;
  expires_at: string | null;
  created_at: string;
  /** True when a HoD assigned this coverage to me (vs my own self-service). */
  assigned_by_hod?: boolean;
  assigned_by_name?: string | null;
  /** Role-explicit projection + canonical one-line summary (shared backend helper). */
  coverer_name?: string | null;
  covers_for_name?: string | null;
  coverage_mode?: string | null;
  summary?: string | null;
}

/** A team coverage row in the HoD management view (coverer covers target). */
export interface TeamCoverageSub {
  id: string;
  subscriber_id: string;
  subscriber_name: string | null;
  target_user_id: string;
  target_user_name: string | null;
  redirect_assignments: boolean;
  expires_at: string | null;
  created_by_id: string | null;
  created_by_name: string | null;
  assigned_by_hod: boolean;
  /** Role-explicit projection + canonical one-line summary (shared backend helper). */
  coverer_name?: string | null;
  covers_for_name?: string | null;
  assigned_by_name?: string | null;
  coverage_mode?: string | null;
  summary?: string | null;
}

export interface CoverageSubCreateResult {
  id: string;
  target_user_id: string;
  is_active: boolean;
  redirect_assignments: boolean;
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

/**
 * Subscribe to a colleague's coverage, optionally with an end date.
 * `redirectAssignments` true = auto-assign their SLA tasks to me (sole coverer);
 * false = notify-only (I'm notified and take over manually). Upserts on (me, target).
 */
export async function subscribeCoverage(
  targetUserId: string,
  expiresAt?: string,
  redirectAssignments = false,
): Promise<CoverageSubCreateResult> {
  const response = await apiFetch(`${BASE}/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      target_user_id: targetUserId,
      redirect_assignments: redirectAssignments,
      ...(expiresAt ? { expires_at: expiresAt } : {}),
    }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to add coverage'));
  }
  return response.json();
}

/** A row where I am the COVERED party: a colleague covers me. */
export interface CoverageForMeSub {
  id: string;
  subscriber_id: string;
  subscriber_name: string | null;
  target_user_id: string;
  target_user_name: string | null;
  is_active: boolean;
  redirect_assignments: boolean;
  expires_at: string | null;
  created_at: string;
  assigned_by_hod: boolean;
  assigned_by_name?: string | null;
  coverer_name?: string | null;
  covers_for_name?: string | null;
  coverage_mode?: string | null;
  summary?: string | null;
}

/** List the colleagues who cover me (I'm the covered party). */
export async function getCoverageForMe(): Promise<CoverageForMeSub[]> {
  const response = await apiFetch(`${BASE}/for-me`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load coverage for me'));
  }
  const body = await response.json();
  return Array.isArray(body?.data) ? (body.data as CoverageForMeSub[]) : [];
}

/**
 * Self-service: nominate a scope-B colleague to cover ME while I'm away.
 * No manager permission required. Upserts on (coverer, me).
 */
export async function nominateCoverer(
  covererId: string,
  expiresAt?: string,
  redirectAssignments = false,
): Promise<{ id: string }> {
  const response = await apiFetch(`${BASE}/nominate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      coverer_id: covererId,
      redirect_assignments: redirectAssignments,
      ...(expiresAt ? { expires_at: expiresAt } : {}),
    }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to nominate coverer'));
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

// --- HoD team coverage (requires notifications.coverage.manage_team) ---------

/** List active coverage across my team scope (coverer OR covered in scope). */
export async function getTeamCoverage(): Promise<TeamCoverageSub[]> {
  const response = await apiFetch(`${BASE}/team`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load team coverage'));
  }
  const body = await response.json();
  return Array.isArray(body?.data) ? (body.data as TeamCoverageSub[]) : [];
}

/** HoD: assign `covererId` to cover `targetUserId` (both in my scope). */
export async function assignCoverage(
  covererId: string,
  targetUserId: string,
  expiresAt?: string,
  redirectAssignments = false,
): Promise<{ id: string }> {
  const response = await apiFetch(`${BASE}/assign`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      coverer_id: covererId,
      target_user_id: targetUserId,
      redirect_assignments: redirectAssignments,
      ...(expiresAt ? { expires_at: expiresAt } : {}),
    }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to assign coverage'));
  }
  return response.json();
}

/** Revoke a specific coverage row by id (coverer or HoD in scope). */
export async function revokeCoverageById(subscriptionId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/manage/${subscriptionId}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to revoke coverage'));
  }
}
