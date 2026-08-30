/**
 * ============================================================================
 * SCM Purchasing and Fulfilment - COVERAGE TIMELINE MOCK STORE (Phase 1 only)
 * ============================================================================
 * Synthetic-but-real fixtures for the dated Coverage Timeline (UAC Group B), so
 * the prototype can be walked with NO backend. Phase 2 flips `USE_COVERAGE_MOCKS`
 * to false in `services/coverageService.ts` and DELETES this file. Nothing else
 * imports it.
 *
 * Every figure below is the worked example from ADR-0011 and the acceptance
 * criteria, not invented data:
 *
 * - `shortfall` scenario: opening 140, demand 135 due 1 Jul, demand 72 due 3 Aug,
 *     a PO of 200 arriving 25 Aug. Balances run 140, 5, -67, 133. First shortfall
 *     is 67 on 3 Aug, and the closing balance is POSITIVE at 133 while that
 *     shortfall is real - which is exactly why supply dated after a demand event
 *     must not offset it (AC-B4). The PO is 22 days late for that order.
 * - `use_pool` scenario: item SRTWT7408, demand 67 against customer bins with
 *     4,397 in the BRW shared pool. Must read "use the pool", never a buy of 67
 *     (AC-B1c). This is the regression case the amendment to ADR-0011 exists for.
 *
 * Deterministic by construction: no `Math.random`, no `Date.now` in the payloads.
 * A SKU maps to a scenario by an explicit override first, then a stable hash, so
 * stepping through the results grid with previous/next walks every state and the
 * same row always shows the same one.
 * ============================================================================
 */
import type {
  CoverageRow,
  CoverageTimeline,
  CoverageTransferAcceptResult,
} from '../types/coverage.types';

/** Phase-1 flag. Phase 2 sets this false and deletes the file. */
export const USE_COVERAGE_MOCKS = false;

/**
 * Counts for the two NEW plan tiles (AC-B9), so a reviewer can see them carrying a
 * real number in Phase 1. **These are the only figures in this file with no engine
 * behind them yet**, because the screens that produce them are later slices:
 * `plan_exceptions` arrives with S5 (recompute-and-diff) and `po_worklist` with S4
 * (the keyed-into-AutoCount worklist). Deleting this file in Phase 2 means feeding
 * both counts from the run summary instead - see the call site on the plan page.
 */
export const MOCK_PLAN_TILE_COUNTS = {
  plan_exceptions: 4,
  po_worklist: 11,
};

/** How long the mock takes to "fetch", so the loading skeleton is actually visible. */
const MOCK_LATENCY_MS = 450;

export type CoverageScenario =
  | 'shortfall'
  | 'use_pool'
  | 'healthy'
  | 'undated'
  | 'empty'
  | 'error';

/**
 * Rotation used for any SKU with no explicit override. Ordered so the first rows a
 * reviewer opens are the two cases the ACs name, and the failure states come after.
 */
const SCENARIO_ROTATION: CoverageScenario[] = [
  'shortfall',
  'use_pool',
  'healthy',
  'undated',
  'empty',
  'error',
];

/** SKUs pinned to a scenario, so the named regression cases are always reachable. */
const SCENARIO_BY_SKU: Record<string, CoverageScenario> = {
  SRTWT7408: 'use_pool',
};

/** Stable non-negative hash of a string. Mirrors `explainerMockStore.skuHash`. */
function skuHash(sku: string): number {
  let h = 0;
  for (let i = 0; i < sku.length; i += 1) {
    h = (h * 31 + sku.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

/** Which fixture a SKU resolves to. Exported so a reviewer can predict the state. */
export function scenarioForSku(sku: string): CoverageScenario {
  const pinned = SCENARIO_BY_SKU[sku.toUpperCase()];
  if (pinned) return pinned;
  return SCENARIO_ROTATION[skuHash(sku) % SCENARIO_ROTATION.length];
}

/** Accumulate signed events into rows, so a fixture can never state a wrong balance. */
function accumulate(
  opening: number,
  events: CoverageRow['event'][],
): { rows: CoverageRow[]; closing: number } {
  const rows: CoverageRow[] = [
    {
      event: {
        at: null,
        qty: 0,
        kind: 'opening',
        ref: '',
        label: 'Opening on hand',
        location: '',
        supply_stage: null,
      },
      balance: opening,
    },
  ];
  let balance = opening;
  for (const event of events) {
    balance += event.qty;
    rows.push({ event, balance });
  }
  return { rows, closing: balance };
}

const HORIZON = {
  horizon_months: 12,
  horizon_end: '2027-07-31',
};

const COMPUTED_AT = '2026-08-03T09:12:00';

// -- 1) The ADR-0011 worked example -------------------------------------------
// 135 due 1 Jul, 72 due 3 Aug, a SHIPMENT of 200 arriving 25 Aug, opening 140.
// Balances 140, 5, -67, 133. Shortfall 67 on 3 Aug. Closing positive at 133.
// The 200 is an allocated shipment, not a purchase order: since 6 Aug 2026 only the SPO
// allocation is supply. A separate 300 sits on a PO with nothing shipped against it, which
// is reported (`qty_ordered_not_incoming`) and is deliberately in none of these balances.

function shortfallFixture(sku: string, productName: string | null): CoverageTimeline {
  const { rows, closing } = accumulate(140, [
    {
      at: '2026-07-01',
      qty: -135,
      kind: 'demand',
      ref: 'SO-2026-0311',
      label: 'Maryam Tuju Residence',
      location: 'BRW-BB',
      supply_stage: null,
    },
    {
      at: '2026-08-03',
      qty: -72,
      kind: 'demand',
      ref: 'SO-2026-0342',
      label: 'Maryam Tuju Residence',
      location: 'BRW-BB',
      supply_stage: null,
    },
    {
      at: '2026-08-25',
      qty: 200,
      kind: 'supply',
      ref: 'SH-2026-0442',
      label: 'Guangdong Sanitary Ware',
      location: 'BRW',
      supply_stage: 'in_transit',
    },
  ]);

  return {
    product_code: sku,
    product_name: productName,
    pool_code: 'BRW',
    locations: ['BRW', 'BRW-BB', 'BRW-HOLD'],
    floor: 0,
    opening_balance: 140,
    rows,
    closing_balance: closing,
    shortfall: {
      at: '2026-08-03',
      qty: 67,
      ref: 'SO-2026-0342',
      label: 'Maryam Tuju Residence',
    },
    peak_deficit: 67,
    availability: {
      own: 0,
      pool: 0,
      other: 18,
      pool_location: 'BRW',
      other_locations: ['BRW-SMC'],
    },
    allocations: [
      { source_type: 'other_project', qty: 18, location: 'BRW-SMC', needs_claim: true },
      { source_type: 'order', qty: 49, location: '', needs_claim: false },
    ],
    buy_qty: 49,
    use_stock: false,
    undated_demand: [],
    transfer_proposals: [
      {
        proposal_ref: 'TP-MWH-0001',
        from_pool_code: 'MWH',
        available_qty: 310,
        qty: 67,
        transfer_cost: 480,
        lead_time_days: 5,
        arrives_at: '2026-08-08',
      },
    ],
    ...HORIZON,
    excluded_event_count: 2,
    unattributed_in_transit_qty: 40,
    qty_ordered_not_incoming: 300,
    unplaceable_demand_qty: 0,
    unplaceable_on_order_qty: 0,
    computed_at: COMPUTED_AT,
  };
}

// -- 2) SRTWT7408: demand 67 against 4,397 in the pool -------------------------
// The first row of the first report anyone read. Netting per warehouse would
// recommend buying 67 units of an item holding 4,397.

function poolFixture(): CoverageTimeline {
  const { rows, closing } = accumulate(4397, [
    {
      at: '2026-08-14',
      qty: -67,
      kind: 'demand',
      ref: 'SO-2026-0357',
      label: 'Bandar Baru Development',
      location: 'BRW-BB',
      supply_stage: null,
    },
    {
      at: '2026-09-30',
      qty: -240,
      kind: 'demand',
      ref: 'SO-2026-0361',
      label: 'Setia Mutiara City',
      location: 'BRW-SMC',
      supply_stage: null,
    },
  ]);

  return {
    product_code: 'SRTWT7408',
    product_name: 'Wall-hung WC 7408',
    pool_code: 'BRW',
    locations: ['BRW', 'BRW-BB', 'BRW-SMC', 'BRW-NTC'],
    floor: 0,
    opening_balance: 4397,
    rows,
    closing_balance: closing,
    shortfall: null,
    peak_deficit: 0,
    availability: {
      own: 0,
      pool: 4397,
      other: 126,
      pool_location: 'BRW',
      other_locations: ['BRW-NTC'],
    },
    allocations: [{ source_type: 'brw', qty: 67, location: 'BRW', needs_claim: false }],
    buy_qty: 0,
    use_stock: true,
    undated_demand: [],
    transfer_proposals: [],
    ...HORIZON,
    excluded_event_count: 0,
    unattributed_in_transit_qty: 0,
    qty_ordered_not_incoming: 0,
    unplaceable_demand_qty: 0,
    unplaceable_on_order_qty: 0,
    computed_at: COMPUTED_AT,
  };
}

// -- 3) Healthy: covered from its own bin, nothing to decide -------------------

function healthyFixture(sku: string, productName: string | null): CoverageTimeline {
  const { rows, closing } = accumulate(880, [
    {
      at: '2026-08-19',
      qty: -120,
      kind: 'demand',
      ref: 'SO-2026-0349',
      label: 'Ipoh Riverside',
      location: 'MWH-IR',
      supply_stage: null,
    },
    {
      at: '2026-09-02',
      qty: 400,
      kind: 'supply',
      ref: 'SHP-2026-0118',
      label: 'Foshan Ceramics',
      location: 'MWH',
      supply_stage: 'in_transit',
    },
    {
      at: '2026-10-15',
      qty: -260,
      kind: 'demand',
      ref: 'SO-2026-0372',
      label: 'Ipoh Riverside',
      location: 'MWH-IR',
      supply_stage: null,
    },
  ]);

  return {
    product_code: sku,
    product_name: productName,
    pool_code: 'MWH',
    locations: ['MWH', 'MWH-IR'],
    floor: 0,
    opening_balance: 880,
    rows,
    closing_balance: closing,
    shortfall: null,
    peak_deficit: 0,
    availability: {
      own: 640,
      pool: 240,
      other: 0,
      pool_location: 'MWH',
      other_locations: [],
    },
    allocations: [],
    buy_qty: 0,
    use_stock: true,
    undated_demand: [],
    transfer_proposals: [],
    ...HORIZON,
    excluded_event_count: 0,
    unattributed_in_transit_qty: 0,
    qty_ordered_not_incoming: 0,
    unplaceable_demand_qty: 0,
    unplaceable_on_order_qty: 0,
    computed_at: COMPUTED_AT,
  };
}

// -- 4) Partial: undated demand, plus events dropped beyond the horizon --------

function undatedFixture(sku: string, productName: string | null): CoverageTimeline {
  const { rows, closing } = accumulate(96, [
    {
      at: '2026-09-11',
      qty: -60,
      kind: 'demand',
      ref: 'SO-2026-0368',
      label: 'Nusantara Trade Centre',
      location: 'WH3-NTC',
      supply_stage: null,
    },
    {
      at: '2026-11-04',
      qty: 150,
      kind: 'supply',
      ref: 'PO-2026-0459',
      label: 'Guangdong Sanitary Ware',
      location: 'WH3',
      supply_stage: 'on_order',
    },
  ]);

  return {
    product_code: sku,
    product_name: productName,
    pool_code: 'WH3',
    locations: ['WH3', 'WH3-NTC'],
    floor: 0,
    opening_balance: 96,
    rows,
    closing_balance: closing,
    shortfall: null,
    peak_deficit: 0,
    availability: {
      own: 36,
      pool: 60,
      other: 0,
      pool_location: 'WH3',
      other_locations: [],
    },
    allocations: [],
    buy_qty: 0,
    use_stock: true,
    undated_demand: [
      { so_number: 'SO-2026-0374', item_code: sku, qty: 48, location: 'WH3-NTC' },
      { so_number: 'SO-2026-0381', item_code: sku, qty: 12, location: 'WH3' },
    ],
    transfer_proposals: [],
    ...HORIZON,
    excluded_event_count: 3,
    unattributed_in_transit_qty: 0,
    qty_ordered_not_incoming: 0,
    unplaceable_demand_qty: 0,
    unplaceable_on_order_qty: 0,
    computed_at: COMPUTED_AT,
  };
}

// -- 5) Empty: stock on hand, nothing dated against it -------------------------

function emptyFixture(sku: string, productName: string | null): CoverageTimeline {
  const { rows, closing } = accumulate(24, []);
  return {
    product_code: sku,
    product_name: productName,
    pool_code: 'DC1',
    locations: ['DC1'],
    floor: 0,
    opening_balance: 24,
    rows,
    closing_balance: closing,
    shortfall: null,
    peak_deficit: 0,
    availability: {
      own: 0,
      pool: 24,
      other: 0,
      pool_location: 'DC1',
      other_locations: [],
    },
    allocations: [],
    buy_qty: 0,
    use_stock: true,
    undated_demand: [],
    transfer_proposals: [],
    ...HORIZON,
    excluded_event_count: 0,
    unattributed_in_transit_qty: 0,
    qty_ordered_not_incoming: 0,
    unplaceable_demand_qty: 0,
    unplaceable_on_order_qty: 0,
    computed_at: COMPUTED_AT,
  };
}

/** Named fixtures, exported so Phase-2 tests can assert against the same figures. */
export const COVERAGE_FIXTURES = {
  shortfall: () => shortfallFixture('SRTBS4832', 'Basin mixer 4832'),
  use_pool: poolFixture,
  healthy: () => healthyFixture('SRTSK2210', 'Kitchen sink 2210'),
  undated: () => undatedFixture('SRTSH6120', 'Shower set 6120'),
  empty: () => emptyFixture('SRTAC0904', 'Accessory pack 0904'),
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

/** The mocked GET. Resolves after a short delay so the skeleton state is real. */
export async function mockCoverageTimeline(
  sku: string,
  productName: string | null,
): Promise<CoverageTimeline> {
  await sleep(MOCK_LATENCY_MS);
  switch (scenarioForSku(sku)) {
    case 'use_pool':
      return poolFixture();
    case 'healthy':
      return healthyFixture(sku, productName);
    case 'undated':
      return undatedFixture(sku, productName);
    case 'empty':
      return emptyFixture(sku, productName);
    case 'error':
      throw new Error('Coverage timeline could not be computed for this item.');
    case 'shortfall':
    default:
      return shortfallFixture(sku, productName);
  }
}

/** The mocked accept. Phase 2 replaces this with the real transfer-proposal POST. */
export async function mockAcceptTransfer(
  proposalRef: string,
): Promise<CoverageTransferAcceptResult> {
  await sleep(MOCK_LATENCY_MS);
  return { proposal_ref: proposalRef, accepted: true, transfer_ref: 'TRF-2026-0087' };
}
