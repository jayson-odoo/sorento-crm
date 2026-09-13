/* -------------------------------------------------------------------------------------
 * Spec visibility policy - PLAN-spec-visibility-policy, slice S1 (Phase 1, MOCKED).
 *
 * Which product spec keys (Thickness, Material, ...) the chatbot may reveal to a
 * contact. One row per tier - contact override > merged market segments > global
 * default - resolved by the BACKEND per turn (`check_access` / `resolve_policy`),
 * same doctrine as `stockVisibilityService`. This file is the FE's only door to that
 * policy; nothing else in the app should build the URL or the body by hand.
 *
 * ===================================================================================
 * API CONTRACT (S2 builds the routes below; every function here is a MOCK until then)
 * ===================================================================================
 *
 * Permission: reads/writes `user_management.contacts.view` / `.edit` (field-reveal
 * precedent) - no new permission slug. Every route lives under the `user_management`
 * module guard, mounted at `/api/v1/user-management/spec-visibility`.
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
 * --- Routes (S2) -----------------------------------------------------------------------
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
 *
 * ===================================================================================
 * MOCK ADAPTER (this slice only - swapped for the routes above in S2)
 * ===================================================================================
 *
 * A module-level store keyed by scope, seeded with the plan's default policy
 * (excludes Thickness + Drainer board / countertop thickness) and the Project
 * segment's empty Hide list, so Save / Remove round-trip on the page without a
 * backend. Retail and untagged contacts have no seeded row, so they read straight
 * through to the default - the real merge-across-segments-for-one-contact rule
 * (UAC AC-9) is server-only and arrives with S2; this mock only resolves "this
 * tier's own row, else the default", which is all a single scope's own card needs.
 * -------------------------------------------------------------------------------- */

/** Registry key -> human label. Mirrors `product_spec_registry.spec_key` (S2 reads the
 * real table; this list is the mock's stand-in for `GET /spec-visibility/keys`). */
const SPEC_VISIBILITY_KEYS: SpecKeyRef[] = [
  { key: 'board_thickness', label: 'Drainer board / countertop thickness' },
  { key: 'finish_colour', label: 'Finish or colour' },
  { key: 'has_drainer_board', label: 'Has a drainer board' },
  { key: 'height', label: 'Height' },
  { key: 'length', label: 'Length' },
  { key: 'material', label: 'Material' },
  { key: 'bowl_count', label: 'Number of bowls' },
  { key: 'steel_grade', label: 'Steel grade' },
  { key: 'surface_texture', label: 'Surface texture' },
  { key: 'thickness', label: 'Thickness' },
  { key: 'width', label: 'Width' },
]; // already sorted by label, as the real `GET /keys` promises

/** Display name for a segment badge/dialog title until the real row carries one. */
const MOCK_SEGMENT_NAMES: Record<string, string> = {
  retail: 'Retail',
  project: 'Project',
};

function segmentLabel(code: string): string {
  return MOCK_SEGMENT_NAMES[code] ?? code.charAt(0).toUpperCase() + code.slice(1);
}

type MockRow = { spec_keys: string[] | null; excluded_spec_keys: string[] | null };

const DEFAULT_ROW: MockRow = { spec_keys: null, excluded_spec_keys: ['thickness', 'board_thickness'] };

/** Seeded rows. Contacts start with none - a contact override is created only on Save. */
const mockStore = new Map<string, MockRow>([
  ['default', DEFAULT_ROW],
  ['segment:project', { spec_keys: null, excluded_spec_keys: [] }],
]);

function storeKey(scope: SpecVisibilityScope): string {
  switch (scope.kind) {
    case 'contact':
      return `contact:${scope.contactId}`;
    case 'segment':
      return `segment:${scope.segmentCode}`;
    default:
      return 'default';
  }
}

function sourceFor(scope: SpecVisibilityScope): SpecVisibilitySource {
  return scope.kind === 'segment' ? 'segment' : scope.kind === 'contact' ? 'contact' : 'default';
}

function sourceLabelFor(scope: SpecVisibilityScope): string | null {
  return scope.kind === 'segment' ? segmentLabel(scope.segmentCode) : null;
}

function toRefs(keys: string[]): SpecKeyRef[] {
  return SPEC_VISIBILITY_KEYS.filter((k) => keys.includes(k.key));
}

/** The registry keys a policy actually hides - what the chatbot consumes (UAC AC-10). */
function hiddenKeys(row: MockRow): string[] {
  if (row.excluded_spec_keys !== null) {
    const registryKeys = new Set(SPEC_VISIBILITY_KEYS.map((k) => k.key));
    return row.excluded_spec_keys.filter((key) => registryKeys.has(key));
  }
  if (row.spec_keys !== null) {
    const shown = new Set(row.spec_keys);
    return SPEC_VISIBILITY_KEYS.filter((k) => !shown.has(k.key)).map((k) => k.key);
  }
  return []; // both null never happens: the 422 guard below refuses that write
}

function buildPolicy(row: MockRow, source: SpecVisibilitySource, sourceLabel: string | null): SpecVisibilityPolicy {
  return {
    specs: row.spec_keys !== null ? toRefs(row.spec_keys) : null,
    excluded_specs: row.excluded_spec_keys !== null ? toRefs(row.excluded_spec_keys) : null,
    hidden: toRefs(hiddenKeys(row)),
    source,
    source_label: sourceLabel,
  };
}

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

/** The path the three verbs call in S2. Kept next to the key so the two cannot drift. */
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
  // MOCK (Phase 1): S2 replaces this body with
  //   const response = await apiFetch(specVisibilityScopePath(scope));
  //   if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load spec visibility'));
  //   return response.json();
  const key = storeKey(scope);
  const ownRow = mockStore.get(key);
  const defaultRow = mockStore.get('default')!;
  const effectiveRow = ownRow ?? defaultRow;
  const effectiveSource = ownRow ? sourceFor(scope) : 'default';
  const effectiveLabel = ownRow ? sourceLabelFor(scope) : null;
  const effective = buildPolicy(effectiveRow, effectiveSource, effectiveLabel);
  const override =
    scope.kind === 'default'
      ? effective
      : ownRow
        ? buildPolicy(ownRow, sourceFor(scope), sourceLabelFor(scope))
        : null;
  return { effective, override };
}

export async function saveSpecVisibility(
  scope: SpecVisibilityScope,
  input: SpecVisibilityInput,
): Promise<SpecVisibilityPolicyResponse> {
  // MOCK (Phase 1): S2 replaces this body with the PUT call documented above.
  if (input.spec_keys !== null && input.excluded_spec_keys !== null) {
    throw new Error('Pick specs to show or to hide, not both.');
  }
  const registryKeys = new Set(SPEC_VISIBILITY_KEYS.map((k) => k.key));
  for (const key of input.spec_keys ?? input.excluded_spec_keys ?? []) {
    if (!registryKeys.has(key)) throw new Error(`Unknown spec key: ${key}`);
  }
  mockStore.set(storeKey(scope), { spec_keys: input.spec_keys, excluded_spec_keys: input.excluded_spec_keys });
  return getSpecVisibility(scope);
}

export async function deleteSpecVisibility(
  scope: SpecVisibilityScope,
): Promise<SpecVisibilityPolicyResponse> {
  // The default row is the floor of the resolution chain and has no DELETE route
  // (same guard as `deleteStockVisibility`); the card offers no Remove there.
  if (scope.kind === 'default') {
    throw new Error('The default spec visibility policy cannot be removed');
  }
  const key = storeKey(scope);
  if (!mockStore.has(key)) {
    throw new Error('This tier has no override to remove');
  }
  mockStore.delete(key);
  return getSpecVisibility(scope);
}

export async function getSpecVisibilityKeys(): Promise<SpecKeyRef[]> {
  // MOCK (Phase 1): S2 replaces this body with a fetch of
  //   GET /api/v1/user-management/spec-visibility/keys
  return SPEC_VISIBILITY_KEYS;
}
