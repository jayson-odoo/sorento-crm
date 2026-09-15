/* -------------------------------------------------------------------------------------
 * Spec visibility policy - PLAN-spec-visibility-policy, slice S2 (wired to the backend).
 *
 * Which product spec keys (Thickness, Material, ...) the chatbot may reveal to a
 * contact. One row per tier - contact override > merged market segments > global
 * default - resolved by the BACKEND per turn (`check_access` / `resolve_policy`),
 * same doctrine as `stockVisibilityService`. This file is the FE's only door to that
 * policy; nothing else in the app should build the URL or the body by hand.
 *
 * ===================================================================================
 * API CONTRACT
 * ===================================================================================
 *
 * Permission: reads `user_management.contacts.view`, writes `user_management.
 * contacts.edit` (field-reveal precedent) - no new permission slug. Mounted at the
 * TOP LEVEL rather than through the `user_management` router's own inclusion, so
 * `/effective` can accept X-API-Key (its module gate is `require_module_enabled_
 * with_api_key("base")`, not the JWT-only one `user_management.router` carries).
 *
 * --- The policy shape every route returns -------------------------------------------
 *
 *   SpecKeyRef = { "key": "thickness", "label": "Thickness" }
 *        // A registry key resolved to its label - the UI never renders a bare key
 *        // slug or a registry id, same "no UUIDs" rule as everywhere else.
 *
 *   Policy = {
 *     "specs": [SpecKeyRef, ...] | null,
 *          // The Show-only list. null = every key visible (no restriction), []
 *          // = no key visible ("No specs"), a list = only these.
 *     "excluded_specs": [SpecKeyRef, ...] | null,
 *          // `specs`'s sibling, the Hide-these list. null = this row is not a
 *          // Hide-these row, [] = nothing hidden ("All specs" under this rule),
 *          // a list = hide exactly these. NEVER both `specs` and `excluded_specs`
 *          // non-null on the same row - that is the 422 below.
 *     "hidden": [SpecKeyRef, ...],
 *          // The net effect: which registry keys this policy actually hides. What
 *          // the chatbot consumes and what the "Hidden today:" line renders. Always
 *          // a list, never null - [] reads "Nothing hidden".
 *     "source": "contact" | "segment" | "default",
 *     "source_label": "Retail" | null
 *          // The market segment NAME when `source == "segment"` (never the code -
 *          // the badge reads "Market segment: Retail"), else null.
 *   }
 *
 *   PolicyResponse = {
 *     "effective": Policy,        // what the chatbot applies to this tier today
 *     "override": Policy | null   // the row stored AT THIS TIER; null = it inherits
 *   }
 *
 *   For the default tier `override` is always present and equals `effective` - the
 *   default row always exists (seeded: excludes `thickness` + `board_thickness`).
 *
 * --- Routes ----------------------------------------------------------------------------
 *
 *   GET  /api/v1/user-management/spec-visibility/effective?contact_id=&space_id=
 *          -> Policy   (api-key allowed; the resolved policy for one contact)
 *
 *   GET|PUT|DELETE /api/v1/user-management/spec-visibility/contacts/{contact_id}
 *          -> PolicyResponse
 *   GET|PUT|DELETE /api/v1/user-management/spec-visibility/segments/{segment_code}
 *          -> PolicyResponse
 *   GET|PUT         /api/v1/user-management/spec-visibility/default
 *          -> PolicyResponse   (no DELETE: the default row is the floor of the chain)
 *
 *   PUT body: { "spec_keys": ["thickness", ...] | null, "excluded_spec_keys": [...] | null }
 *          Both fields REQUIRED (nullable, never defaulted) and replace the row
 *          wholesale, same reasoning as stock visibility's warehouse lists: an
 *          omitted key would silently widen the policy on the next Save. Both
 *          non-null -> 422 "Pick specs to show or to hide, not both." An unknown or
 *          inactive registry key -> 422 naming it. An unknown segment code -> 404.
 *
 *   DELETE: hard delete of the override row; 404 on a tier that already inherits.
 *
 *   GET /api/v1/user-management/spec-visibility/keys -> [SpecKeyRef, ...]
 *          The active registry keys, sorted by label, for the picker. A separate
 *          route (not the products list) so a contacts admin does not need
 *          `master_data.products.view` to open this card.
 * -------------------------------------------------------------------------------- */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/** All three answer tiers. */
export type SpecVisibilitySource = 'contact' | 'segment' | 'default';

export interface SpecKeyRef {
  key: string;
  label: string;
}

export interface SpecVisibilityPolicy {
  /** null = every key visible; [] = none. */
  specs: SpecKeyRef[] | null;
  /** `specs`'s sibling: null = not a Hide-these row, [] = nothing hidden, a list = hide these. */
  excluded_specs: SpecKeyRef[] | null;
  /** The net effect - what the chatbot hides and what "Hidden today:" renders. */
  hidden: SpecKeyRef[];
  source: SpecVisibilitySource;
  /** Market segment NAME when `source` is `segment`, else null. */
  source_label: string | null;
}

export interface SpecVisibilityPolicyResponse {
  effective: SpecVisibilityPolicy;
  /** The row stored at the requested tier. null = this tier inherits. */
  override: SpecVisibilityPolicy | null;
}

export interface SpecVisibilityInput {
  /** null = every key visible; [] = none. Required-nullable, replaces wholesale. */
  spec_keys: string[] | null;
  /** `spec_keys`'s sibling: null = not this rule, [] = hide none, a list = hide these. */
  excluded_spec_keys: string[] | null;
}

/**
 * Which tier a surface edits. One component serves the contact page, the market
 * segment admin and the settings default, so the tier is a prop rather than three
 * copies (same convention as `StockVisibilityScope`).
 */
export type SpecVisibilityScope =
  | { kind: 'contact'; contactId: string }
  | { kind: 'segment'; segmentCode: string }
  | { kind: 'default' };

/** react-query key, and the route segment each scope maps to. */
export function specVisibilityScopeKey(scope: SpecVisibilityScope): string[] {
  switch (scope.kind) {
    case 'contact':
      return ['spec-visibility', 'contact', scope.contactId];
    case 'segment':
      return ['spec-visibility', 'segment', scope.segmentCode];
    default:
      return ['spec-visibility', 'default'];
  }
}

/** The path the three verbs call. Kept next to the key so the two cannot drift. */
export function specVisibilityScopePath(scope: SpecVisibilityScope): string {
  switch (scope.kind) {
    case 'contact':
      return `/api/v1/user-management/spec-visibility/contacts/${encodeURIComponent(scope.contactId)}`;
    case 'segment':
      return `/api/v1/user-management/spec-visibility/segments/${encodeURIComponent(scope.segmentCode)}`;
    default:
      return '/api/v1/user-management/spec-visibility/default';
  }
}

export async function getSpecVisibility(
  scope: SpecVisibilityScope,
): Promise<SpecVisibilityPolicyResponse> {
  const response = await apiFetch(specVisibilityScopePath(scope));
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load spec visibility'));
  }
  return response.json();
}

export async function saveSpecVisibility(
  scope: SpecVisibilityScope,
  input: SpecVisibilityInput,
): Promise<SpecVisibilityPolicyResponse> {
  const response = await apiFetch(specVisibilityScopePath(scope), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save spec visibility'));
  }
  return response.json();
}

export async function deleteSpecVisibility(
  scope: SpecVisibilityScope,
): Promise<SpecVisibilityPolicyResponse> {
  // The default row is the floor of the resolution chain and has no DELETE route
  // (same guard as `deleteStockVisibility`); the card offers no Remove there.
  if (scope.kind === 'default') {
    throw new Error('The default spec visibility policy cannot be removed');
  }
  const response = await apiFetch(specVisibilityScopePath(scope), { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to remove spec visibility'));
  }
  return response.json();
}

export async function getSpecVisibilityKeys(): Promise<SpecKeyRef[]> {
  const response = await apiFetch('/api/v1/user-management/spec-visibility/keys');
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load spec keys'));
  }
  return response.json();
}
