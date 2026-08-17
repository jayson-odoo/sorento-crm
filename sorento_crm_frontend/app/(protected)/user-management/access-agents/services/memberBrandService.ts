import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * Brand tags on a team membership - the second routing axis, alongside market
 * segments. A member tagged `mocha` only takes Mocha work; a member with no tags
 * serves every brand. When nobody in the team carries the brand a conversation
 * asks for, the whole team round-robins.
 *
 * Keyed by (team_id, user_id) like the segment assignment, so the same person can
 * serve different brands in different teams.
 *
 *   GET /api/v1/user-management/teams/{team}/members/{user}/brands  -> { codes: string[] }
 *   PUT  same path, body { codes: string[] }                        -> { codes: string[] }
 *
 * Codes are lower-case `brands.brand_code` values; the PUT replaces the whole set
 * and an empty array clears it back to "serves all".
 */

function memberBrandsPath(teamId: string, userId: string): string {
  return `/api/user-management/teams/${encodeURIComponent(teamId)}/members/${encodeURIComponent(
    userId,
  )}/brands`;
}

export async function getMemberBrands(
  teamId: string,
  userId: string,
): Promise<string[]> {
  const response = await apiFetch(memberBrandsPath(teamId, userId));
  if (!response.ok)
    throw new Error(
      await extractApiError(response, 'Failed to fetch member brands'),
    );
  const data = (await response.json()) as { codes?: string[] };
  return Array.isArray(data.codes) ? data.codes : [];
}

export async function setMemberBrands(
  teamId: string,
  userId: string,
  codes: string[],
): Promise<string[]> {
  const response = await apiFetch(memberBrandsPath(teamId, userId), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ codes }),
  });
  if (!response.ok)
    throw new Error(
      await extractApiError(response, 'Failed to update member brands'),
    );
  const data = (await response.json()) as { codes?: string[] };
  return Array.isArray(data.codes) ? data.codes : [];
}
