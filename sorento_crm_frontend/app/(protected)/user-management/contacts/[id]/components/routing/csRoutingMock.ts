/**
 * Feature service — Contact CS-routing predicate rules (R2). Phase-2 WIRED to the
 * real FastAPI endpoints under /api/v1/user-management/contacts.
 *
 *   GET    .../{contactId}/cs-routing                → { pins: RoutingRule[] }
 *   GET    .../cs-routing/candidates                 → { candidates: CsCandidate[] }
 *   GET    .../cs-routing/fields?use_case=<uc>       → { fields: RoutableField[] }
 *   PUT    .../{contactId}/cs-routing/{use_case}     body { cs_pic_user_id, match_conditions, priority }
 *   DELETE .../{contactId}/cs-routing/{use_case}     (clears all rows for the use_case)
 *
 * Uniqueness: one rule per (contact, use_case, canonical(match_conditions)). Save
 * = replace: clear the affected use_cases, then PUT each rule with priority = list
 * order (lowest priority wins in the resolver).
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { Predicate, RoutableField } from './predicateTypes';

const BASE = '/api/v1/user-management/contacts';

export interface CsCandidate {
  id: string;
  name: string;
  email: string;
}

export interface RoutingRule {
  id: string;
  use_case: string;
  cs_pic_user_id: string | null;
  cs_pic_name: string | null;
  match_conditions: Predicate[];
  priority: number;
}

export const CS_USE_CASES: { key: string; label: string }[] = [
  { key: 'purchase_request', label: 'Purchase Request' },
  { key: 'sponsorship_form', label: 'Sponsorship Form' },
];

export async function getRoutingRules(contactId: string): Promise<RoutingRule[]> {
  const r = await apiFetch(`${BASE}/${contactId}/cs-routing`);
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load routing rules'));
  const data = await r.json();
  const pins = (data?.pins ?? []) as RoutingRule[];
  return pins.slice().sort((a, b) => a.priority - b.priority);
}

export async function getCsCandidates(): Promise<CsCandidate[]> {
  const r = await apiFetch(`${BASE}/cs-routing/candidates`);
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load CS candidates'));
  const data = await r.json();
  return (data?.candidates ?? []) as CsCandidate[];
}

export async function getRoutableFields(useCase: string): Promise<RoutableField[]> {
  const r = await apiFetch(`${BASE}/cs-routing/fields?use_case=${encodeURIComponent(useCase)}`);
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load routable fields'));
  const data = await r.json();
  return (data?.fields ?? []) as RoutableField[];
}

/**
 * Replace this contact's routing config with `rules`. Clears every affected
 * use_case (current + incoming), then PUTs each complete rule with priority = its
 * position in the list. Rules without a selected CS PIC are skipped (incomplete).
 * Returns the freshly-persisted rules (with server-assigned ids).
 */
export async function saveRoutingRules(
  contactId: string,
  rules: RoutingRule[],
): Promise<RoutingRule[]> {
  const current = await getRoutingRules(contactId).catch(() => [] as RoutingRule[]);
  const useCases = new Set<string>([
    ...current.map((r) => r.use_case),
    ...rules.map((r) => r.use_case),
  ]);
  for (const uc of useCases) {
    const del = await apiFetch(`${BASE}/${contactId}/cs-routing/${encodeURIComponent(uc)}`, {
      method: 'DELETE',
    });
    if (!del.ok && del.status !== 404) {
      throw new Error(await extractApiError(del, 'Failed to clear routing rules'));
    }
  }
  // Re-create in list order → priority = index (lowest wins).
  for (let i = 0; i < rules.length; i++) {
    const rule = rules[i];
    if (!rule.cs_pic_user_id) continue; // incomplete row — skip
    const put = await apiFetch(
      `${BASE}/${contactId}/cs-routing/${encodeURIComponent(rule.use_case)}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cs_pic_user_id: rule.cs_pic_user_id,
          match_conditions: rule.match_conditions ?? [],
          priority: i,
        }),
      },
    );
    if (!put.ok) throw new Error(await extractApiError(put, 'Failed to save routing rule'));
  }
  return getRoutingRules(contactId);
}
