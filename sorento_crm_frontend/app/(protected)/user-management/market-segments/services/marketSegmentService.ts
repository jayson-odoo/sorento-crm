import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * Market segments (retail / project) drive CS-team routing: a contact tagged
 * `retail` is routed only to CS members serving retail, `project` only to
 * project members, both = either. Untagged contact / member = matches all.
 *
 * Catalog CRUD + contact-assignment + member-assignment all live under the
 * user-management backend domain. See PLAN-cs-team-market-segment-routing.md.
 */

export interface MarketSegment {
  code: string;
  name: string;
  description: string | null;
  is_active: boolean;
  sort_order: number | null;
}

export interface MarketSegmentCreate {
  code: string;
  name: string;
  description?: string | null;
  is_active?: boolean;
  sort_order?: number | null;
}

export type MarketSegmentUpdate = Partial<
  Pick<MarketSegment, 'name' | 'description' | 'is_active' | 'sort_order'>
>;

const base = '/api/user-management/market-segments';

// ---- Catalog CRUD ---------------------------------------------------------

export async function listMarketSegments(activeOnly = false): Promise<MarketSegment[]> {
  const url = activeOnly ? `${base}/?active_only=true` : `${base}/`;
  const response = await apiFetch(url);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to fetch market segments'));
  const data = await response.json();
  return Array.isArray(data) ? data : [];
}

export async function createMarketSegment(body: MarketSegmentCreate): Promise<MarketSegment> {
  const response = await apiFetch(`${base}/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to create market segment'));
  return response.json();
}

export async function updateMarketSegment(
  code: string,
  body: MarketSegmentUpdate,
): Promise<MarketSegment> {
  const response = await apiFetch(`${base}/${encodeURIComponent(code)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to update market segment'));
  return response.json();
}

export async function deleteMarketSegment(code: string): Promise<void> {
  const response = await apiFetch(`${base}/${encodeURIComponent(code)}`, { method: 'DELETE' });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to delete market segment'));
}

// ---- Contact assignment ---------------------------------------------------

export async function getContactMarketSegments(contactId: string): Promise<string[]> {
  const response = await apiFetch(
    `/api/user-management/contacts/${encodeURIComponent(contactId)}/market-segments`,
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to fetch contact market segments'));
  const data = (await response.json()) as { codes?: string[] };
  return Array.isArray(data.codes) ? data.codes : [];
}

export async function setContactMarketSegments(
  contactId: string,
  codes: string[],
): Promise<string[]> {
  const response = await apiFetch(
    `/api/user-management/contacts/${encodeURIComponent(contactId)}/market-segments`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ codes }),
    },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to update contact market segments'));
  const data = (await response.json()) as { codes?: string[] };
  return Array.isArray(data.codes) ? data.codes : [];
}

// ---- Team-member assignment (keyed by team_id + user_id) ------------------

export async function getMemberMarketSegments(
  teamId: string,
  userId: string,
): Promise<string[]> {
  const response = await apiFetch(
    `/api/user-management/teams/${encodeURIComponent(teamId)}/members/${encodeURIComponent(
      userId,
    )}/market-segments`,
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to fetch member market segments'));
  const data = (await response.json()) as { codes?: string[] };
  return Array.isArray(data.codes) ? data.codes : [];
}

export async function setMemberMarketSegments(
  teamId: string,
  userId: string,
  codes: string[],
): Promise<string[]> {
  const response = await apiFetch(
    `/api/user-management/teams/${encodeURIComponent(teamId)}/members/${encodeURIComponent(
      userId,
    )}/market-segments`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ codes }),
    },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to update member market segments'));
  const data = (await response.json()) as { codes?: string[] };
  return Array.isArray(data.codes) ? data.codes : [];
}
