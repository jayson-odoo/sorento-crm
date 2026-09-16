import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * Market segments (retail / project) drive CS-team routing: a contact tagged
 * `retail` is routed only to CS members serving retail, `project` only to
 * project members, both = either. Untagged contact / member = matches all.
 *
 * Catalog CRUD + contact-assignment + member-assignment all live under the
 * user-management backend domain. See PLAN-cs-team-market-segment-routing.md.
 *
 * ---------------------------------------------------------------------------
 * API CONTRACT - `portal_form_types`, written in Phase 1, built to in Phase 2
 * ---------------------------------------------------------------------------
 * PLAN-portal-forms-market-segment D1/D3/D4: the group source for a portal
 * form grant moves from contact access types to market segments. Every
 * contact already gets the four legacy kinds (`SUPPORTED_TYPES`) by default -
 * a segment's `portal_form_types` can only grant MORE on top of that base
 * (today: `price_tag_request`), never take a base kind away.
 *
 * `GET /api/v1/user-management/market-segments/` and the create/update routes
 * carry `portal_form_types: string[]` in the same payload as the other
 * fields (list, echo on create/update; omitted on update leaves it alone).
 * 422 for a kind outside `GRANTABLE_PORTAL_FORM_TYPES` beyond the base four.
 */

export interface MarketSegment {
  code: string;
  name: string;
  description: string | null;
  is_active: boolean;
  sort_order: number | null;
  /**
   * Contacts tagged with a requestor-selectable segment are the ones offered in
   * the "Requested by" / "Sales person" picker on PR / SF / stock inquiry. This
   * flag is the admin-visible indicator for which segments feed that dropdown
   * (UAC-requested-by-contact-routing group D).
   */
  is_requestor_selectable: boolean;
  /**
   * Portal forms this segment grants BEYOND the base four every contact
   * already has (today: `price_tag_request`). Empty = this segment grants
   * nothing extra (PLAN-portal-forms-market-segment D3/D4).
   */
  portal_form_types: string[];
}

export interface MarketSegmentCreate {
  code: string;
  name: string;
  description?: string | null;
  is_active?: boolean;
  sort_order?: number | null;
  is_requestor_selectable?: boolean;
  portal_form_types?: string[];
}

export type MarketSegmentUpdate = Partial<
  Pick<
    MarketSegment,
    | 'name'
    | 'description'
    | 'is_active'
    | 'sort_order'
    | 'is_requestor_selectable'
    | 'portal_form_types'
  >
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
