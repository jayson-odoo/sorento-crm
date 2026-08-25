/* -------------------------------------------------------------------------------------
 * Stock visibility policy - PLAN-stock-visibility-policy, slice S1 (Phase 1).
 *
 * Which warehouses a chatbot contact may be told about, and in which of the three
 * answer shapes. One row per tier: contact override > contact access type > global
 * default, resolved by the BACKEND inside `GET /inventory/stock/balance` (the preflight
 * endpoint below is a convenience, never the mechanism - same doctrine as
 * `agent_field_access`).
 *
 * ===================================================================================
 * PHASE 1 NOTICE
 * ===================================================================================
 * Nothing here talks to the API yet. S2 builds the routes, S4 swaps the bodies of the
 * exported functions for `apiFetch` + `extractApiError` calls against the contract
 * below and deletes the `MOCK BACKEND` block at the bottom. The exported signatures,
 * types and error shape are what S4 must keep - the UI is written against them.
 *
 * ===================================================================================
 * API CONTRACT (built in S2, wired in S4)
 * ===================================================================================
 *
 * Permission: reads `inventory.stock.view`, writes `inventory.stock.edit`.
 * Every route lives under the `inventory` module guard.
 *
 * --- The policy shape every route returns -------------------------------------------
 *
 *   Policy = {
 *     "mode": "detailed" | "compact" | "availability",
 *     "warehouses": [{ "id": "<uuid>", "code": "BRW", "name": "Main Warehouse" }] | null,
 *          // null  = every active warehouse (the stored `warehouse_ids` is NULL)
 *          // []    = no warehouse at all, so the contact is told about no stock
 *          // Resolved rows, not bare ids: the UI renders `CODE - name` and never a UUID.
 *     "source": "contact" | "access_type" | "default",
 *     "source_label": "Dealer" | null
 *          // The access type NAME when source == "access_type", else null. A NAME, not
 *          // the code, because the badge reads "Access type: Dealer".
 *   }
 *
 *   PolicyResponse = {
 *     "effective": Policy,        // what the chatbot applies to this tier today
 *     "override": Policy | null   // the row stored AT THIS TIER; null = the tier inherits
 *   }
 *
 *   For the default tier `override` is always present and equals `effective` - the
 *   default row always exists (seeded inert: detailed / all warehouses).
 *
 * --- Routes --------------------------------------------------------------------------
 *
 *   GET    /api/v1/inventory/stock-visibility/effective?contact_id=&space_id=
 *            -> Policy      (external principal + API key; the n8n preflight convenience)
 *
 *   GET    /api/v1/inventory/stock-visibility/contacts/{contact_id}    -> PolicyResponse
 *   PUT    /api/v1/inventory/stock-visibility/contacts/{contact_id}    -> PolicyResponse
 *            body: { "mode": "compact", "warehouse_ids": ["<uuid>", ...] | null }
 *            Upsert. `warehouse_ids` is replaced wholesale, never merged.
 *   DELETE /api/v1/inventory/stock-visibility/contacts/{contact_id}    -> PolicyResponse
 *            Hard delete of the override row. The body carries the tier the contact
 *            falls back to, so the UI re-renders the inherited policy without a refetch.
 *
 *   GET|PUT|DELETE /api/v1/inventory/stock-visibility/access-types/{code}
 *            Same three shapes, keyed by `contact_access_types.code`.
 *            PUT with an unknown code -> 404.
 *
 *   GET|PUT /api/v1/inventory/stock-visibility/default
 *            No DELETE: the default row is the floor of the resolution chain, so the UI
 *            offers no Remove on that surface.
 *
 *   422 on: `mode` outside the three; a `warehouse_ids` entry that is not an existing
 *   warehouse. `detail` carries the message the UI toasts via `extractApiError`.
 *
 * --- Warehouse pickers (existing route, one new filter) ------------------------------
 *
 *   GET /api/v1/inventory/warehouses?query=&is_active=true&page=1&limit=50
 *            Already exists. Server search, which is what the Locations picker uses -
 *            a client-side capped list is not allowed for a master this size.
 *
 *   GET /api/v1/inventory/warehouses?segment=dealer&is_active=true&limit=200
 *            The "Dealer pool" preset. `segment` is a NEW query filter on the existing
 *            route (the column `warehouses.segment` is already there and already on
 *            `WarehouseResponse`); S2 adds the filter. Documented here because the
 *            preset is the only caller and the PLAN's API section did not list it.
 * ----------------------------------------------------------------------------------- */

/** The three answer shapes. Ordered loosest -> most restrictive; the merge below relies on it. */
export type StockVisibilityMode = 'detailed' | 'compact' | 'availability';

export const STOCK_VISIBILITY_MODE_ORDER: StockVisibilityMode[] = [
  'detailed',
  'compact',
  'availability',
];

export const STOCK_VISIBILITY_MODE_LABELS: Record<StockVisibilityMode, string> = {
  detailed: 'Detailed',
  compact: 'Compact',
  availability: 'Availability only',
};

export type StockVisibilitySource = 'contact' | 'access_type' | 'default';

/** Resolved warehouse, so the UI can render `CODE - name` and never a UUID. */
export interface StockVisibilityWarehouse {
  id: string;
  code: string;
  name: string | null;
}

export interface StockVisibilityPolicy {
  mode: StockVisibilityMode;
  /** null = every active warehouse; [] = none at all. */
  warehouses: StockVisibilityWarehouse[] | null;
  source: StockVisibilitySource;
  /** Access type NAME when `source` is `access_type`, else null. */
  source_label: string | null;
}

export interface StockVisibilityPolicyResponse {
  effective: StockVisibilityPolicy;
  /** The row stored at the requested tier. null = this tier inherits. */
  override: StockVisibilityPolicy | null;
}

export interface StockVisibilityInput {
  mode: StockVisibilityMode;
  /** null = every active warehouse; [] = none. Replaces the stored list wholesale. */
  warehouse_ids: string[] | null;
}

/**
 * Which tier a surface edits. One component serves the contact page, the access type
 * admin and the settings default, so the tier is a prop rather than three copies.
 *
 * `accessTypeCodes` / `accessTypeName` are PHASE 1 MOCK INPUT ONLY: the backend resolves
 * the access-type tier itself from `contact_id`, and S4 drops both fields when it swaps
 * the mock for `apiFetch`. They are here so a real contact on a real page reaches the
 * inherited-from-access-type state during the S1 browser run.
 */
export type StockVisibilityScope =
  | { kind: 'contact'; contactId: string; accessTypeCodes?: string[] }
  | { kind: 'access_type'; accessTypeCode: string; accessTypeName?: string }
  | { kind: 'default' };

/** react-query key, and (in S4) the route segment each scope maps to. */
export function stockVisibilityScopeKey(scope: StockVisibilityScope): string[] {
  switch (scope.kind) {
    case 'contact':
      return ['stock-visibility', 'contact', scope.contactId];
    case 'access_type':
      return ['stock-visibility', 'access-type', scope.accessTypeCode];
    default:
      return ['stock-visibility', 'default'];
  }
}

/** The path S4 calls. Kept next to the key so the two cannot drift. */
export function stockVisibilityScopePath(scope: StockVisibilityScope): string {
  switch (scope.kind) {
    case 'contact':
      return `/api/v1/inventory/stock-visibility/contacts/${scope.contactId}`;
    case 'access_type':
      return `/api/v1/inventory/stock-visibility/access-types/${scope.accessTypeCode}`;
    default:
      return '/api/v1/inventory/stock-visibility/default';
  }
}

export async function getStockVisibility(
  scope: StockVisibilityScope,
): Promise<StockVisibilityPolicyResponse> {
  await mockLatency();
  return mockRead(scope);
}

export async function saveStockVisibility(
  scope: StockVisibilityScope,
  input: StockVisibilityInput,
): Promise<StockVisibilityPolicyResponse> {
  await mockLatency();
  return mockWrite(scope, input);
}

export async function deleteStockVisibility(
  scope: StockVisibilityScope,
): Promise<StockVisibilityPolicyResponse> {
  await mockLatency();
  return mockDelete(scope);
}

/** Locations picker: server search, one page at a time. */
export async function searchStockVisibilityWarehouses(
  query: string,
): Promise<StockVisibilityWarehouse[]> {
  await mockLatency();
  return mockSearchWarehouses(query);
}

/** "Dealer pool" preset: every active warehouse whose `segment` is `dealer`. */
export async function getDealerPoolWarehouses(): Promise<StockVisibilityWarehouse[]> {
  await mockLatency();
  return MOCK_WAREHOUSES.filter((w) => w.segment === 'dealer').map(toWarehouseRef);
}

/* =====================================================================================
 * MOCK BACKEND - Phase 1 only. S4 deletes everything below this line.
 * =====================================================================================
 *
 * In-memory and module-scoped, so a save on one surface is visible on the next read
 * from any surface within the same page session. It mirrors the resolution the backend
 * will do (S2): contact override, else the most restrictive matching access-type row,
 * else the default row.
 *
 * Seeded so all three badge states are reachable without writing anything:
 *   - MOCK_CONTACT_WITH_OVERRIDE     -> "Contact override"  (compact, two locations)
 *   - MOCK_CONTACT_WITH_ACCESS_TYPE  -> "Access type: Dealer" (availability, dealer pool)
 *   - MOCK_CONTACT_INHERITING_DEFAULT -> "Default"          (detailed, all locations)
 * Any other contact id resolves through its `accessTypeCodes` hint, then the default -
 * which is what a real contact on the real page hits.
 */

export const MOCK_CONTACT_WITH_OVERRIDE = 'mock-contact-override';
export const MOCK_CONTACT_WITH_ACCESS_TYPE = 'mock-contact-access-type';
export const MOCK_CONTACT_INHERITING_DEFAULT = 'mock-contact-default';

interface MockWarehouse extends StockVisibilityWarehouse {
  segment: 'dealer' | 'project';
}

/** `pool_warehouse_id` / `segment` already exist on `warehouses`; codes are the real ones. */
const MOCK_WAREHOUSES: MockWarehouse[] = [
  { id: 'wh-brw', code: 'BRW', name: 'Rawang Main Warehouse', segment: 'dealer' },
  { id: 'wh-mwh', code: 'MWH', name: 'Meru Warehouse', segment: 'dealer' },
  { id: 'wh-dc1', code: 'DC1', name: 'Distribution Centre 1', segment: 'dealer' },
  { id: 'wh-brw-bb', code: 'BRW-BB', name: 'Rawang Bulk Bay', segment: 'project' },
  { id: 'wh-brw-ib', code: 'BRW-IB', name: 'Rawang Inbound Bay', segment: 'project' },
  { id: 'wh-jhb1', code: 'JHB1', name: 'Johor Bahru Hub', segment: 'project' },
  { id: 'wh-png1', code: 'PNG1', name: 'Penang Hub', segment: 'project' },
  { id: 'wh-kch1', code: 'KCH1', name: 'Kuching Depot', segment: 'project' },
];

function toWarehouseRef(w: MockWarehouse): StockVisibilityWarehouse {
  return { id: w.id, code: w.code, name: w.name };
}

function warehouseRefs(ids: string[] | null): StockVisibilityWarehouse[] | null {
  if (ids === null) return null;
  return MOCK_WAREHOUSES.filter((w) => ids.includes(w.id)).map(toWarehouseRef);
}

interface MockRow {
  mode: StockVisibilityMode;
  warehouse_ids: string[] | null;
}

const mockContactRows = new Map<string, MockRow>([
  [MOCK_CONTACT_WITH_OVERRIDE, { mode: 'compact', warehouse_ids: ['wh-brw', 'wh-brw-bb'] }],
]);

const mockAccessTypeRows = new Map<string, MockRow & { name: string }>([
  [
    'dealer',
    {
      name: 'Dealer',
      mode: 'availability',
      warehouse_ids: ['wh-brw', 'wh-mwh', 'wh-dc1'],
    },
  ],
]);

let mockDefaultRow: MockRow = { mode: 'detailed', warehouse_ids: null };

/** Access types held by the seeded contacts; real contacts pass their own via the scope. */
const mockContactAccessTypes = new Map<string, string[]>([
  [MOCK_CONTACT_WITH_ACCESS_TYPE, ['dealer']],
  [MOCK_CONTACT_WITH_OVERRIDE, ['dealer']],
  [MOCK_CONTACT_INHERITING_DEFAULT, []],
]);

function mockLatency(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 200));
}

function policyFrom(
  row: MockRow,
  source: StockVisibilitySource,
  sourceLabel: string | null = null,
): StockVisibilityPolicy {
  return {
    mode: row.mode,
    warehouses: warehouseRefs(row.warehouse_ids),
    source,
    source_label: sourceLabel,
  };
}

/**
 * Most restrictive wins, exactly as the S2 resolver must: highest mode in
 * STOCK_VISIBILITY_MODE_ORDER, warehouses intersected with NULL read as "all".
 */
function mergeAccessTypeRows(codes: string[]): { row: MockRow; label: string } | null {
  const matched = codes
    .map((code) => mockAccessTypeRows.get(code))
    .filter((r): r is MockRow & { name: string } => !!r);
  if (matched.length === 0) return null;

  let mode: StockVisibilityMode = 'detailed';
  let ids: string[] | null = null;
  for (const row of matched) {
    if (
      STOCK_VISIBILITY_MODE_ORDER.indexOf(row.mode) > STOCK_VISIBILITY_MODE_ORDER.indexOf(mode)
    ) {
      mode = row.mode;
    }
    if (row.warehouse_ids === null) continue;
    ids = ids === null ? [...row.warehouse_ids] : ids.filter((id) => row.warehouse_ids!.includes(id));
  }
  return { row: { mode, warehouse_ids: ids }, label: matched.map((r) => r.name).join(', ') };
}

function mockContactAccessTypeCodes(scope: {
  contactId: string;
  accessTypeCodes?: string[];
}): string[] {
  return scope.accessTypeCodes ?? mockContactAccessTypes.get(scope.contactId) ?? [];
}

function mockRead(scope: StockVisibilityScope): StockVisibilityPolicyResponse {
  if (scope.kind === 'default') {
    return {
      effective: policyFrom(mockDefaultRow, 'default'),
      override: policyFrom(mockDefaultRow, 'default'),
    };
  }

  if (scope.kind === 'access_type') {
    const row = mockAccessTypeRows.get(scope.accessTypeCode);
    if (!row) {
      return { effective: policyFrom(mockDefaultRow, 'default'), override: null };
    }
    const policy = policyFrom(row, 'access_type', row.name);
    return { effective: policy, override: policy };
  }

  const own = mockContactRows.get(scope.contactId);
  if (own) {
    const policy = policyFrom(own, 'contact');
    return { effective: policy, override: policy };
  }
  const inherited = mergeAccessTypeRows(mockContactAccessTypeCodes(scope));
  if (inherited) {
    return {
      effective: policyFrom(inherited.row, 'access_type', inherited.label),
      override: null,
    };
  }
  return { effective: policyFrom(mockDefaultRow, 'default'), override: null };
}

function mockWrite(
  scope: StockVisibilityScope,
  input: StockVisibilityInput,
): StockVisibilityPolicyResponse {
  const row: MockRow = { mode: input.mode, warehouse_ids: input.warehouse_ids };
  if (scope.kind === 'default') {
    mockDefaultRow = row;
  } else if (scope.kind === 'access_type') {
    mockAccessTypeRows.set(scope.accessTypeCode, {
      ...row,
      name: scope.accessTypeName ?? scope.accessTypeCode,
    });
  } else {
    mockContactRows.set(scope.contactId, row);
  }
  return mockRead(scope);
}

function mockDelete(scope: StockVisibilityScope): StockVisibilityPolicyResponse {
  if (scope.kind === 'default') {
    throw new Error('The default stock visibility policy cannot be removed');
  }
  if (scope.kind === 'access_type') {
    mockAccessTypeRows.delete(scope.accessTypeCode);
  } else {
    mockContactRows.delete(scope.contactId);
  }
  return mockRead(scope);
}

function mockSearchWarehouses(query: string): StockVisibilityWarehouse[] {
  const q = query.trim().toLowerCase();
  const matched = q
    ? MOCK_WAREHOUSES.filter(
        (w) =>
          w.code.toLowerCase().includes(q) || (w.name ?? '').toLowerCase().includes(q),
      )
    : MOCK_WAREHOUSES;
  return matched.slice(0, 50).map(toWarehouseRef);
}
