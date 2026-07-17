/**
 * ============================================================================
 * SCM M4 — Cash co-pilot DETERMINISTIC MOCK  (Phase 1 only)
 * ============================================================================
 * PROTOTYPE DATA. No network, no `Math.random`, no `Date` — every value is a
 * hand-authored constant so the funded/deferred split renders identically on
 * every load and the greedy skip-overflow allocation is fully reproducible.
 *
 * Phase 2 deletes this file (or keeps it only for vitest fixtures) and flips
 * `USE_M4_MOCKS` to false in `services/reorderRunService.ts`; the funding then
 * comes from `GET /scm/reorder-runs/{id}/recommendations?budget=X` and the same
 * `computeFunding` helper below runs client-side for the live slider what-if.
 *
 * `computeFunding` IS the deterministic allocation (M4-D3, greedy by rank,
 * skip-overflow-continue) and is exported for reuse in Phase 2 + tests — the
 * mock only supplies the frozen recommendation set it operates on.
 *
 * The buy set is intentionally a MIX of costed (margin factor present) and
 * uncosted (margin DROPPED, urgency-dominant) SKUs — mirroring the real data
 * where most SKUs have no cost (M4-D14). The frozen `rank`/`cash_impact` are
 * tuned so a mid-range budget lands the funded boundary mid-list with a big
 * item SKIPPED and a smaller later item still FUNDED (skip-overflow visible).
 * ============================================================================
 */
import type {
  RankFactor,
  ReorderRecommendation,
  SupplierChoice,
} from '../types/reorder.types';
// The deterministic allocator + score now live in the production lib
// (`reorderCashAllocation`); the mock only supplies the frozen fixture set it
// operates on. Re-exported for backward-compat with existing imports/tests.
import {
  BUDGET_STEP,
  computeFunding,
  defaultBudgetFor,
  scoreFromFactors,
  sliderMaxFor,
  totalCostedCash,
  type FundingResult,
} from './reorderCashAllocation';

export {
  BUDGET_STEP,
  computeFunding,
  scoreFromFactors,
  type FundingResult,
};

/** Default cash_ranking_policy weights (M4-D1 default: urgency + margin dominant). */
const WEIGHTS: Record<RankFactor['key'], number> = {
  urgency: 0.35,
  margin: 0.25,
  abc: 0.15,
  priority: 0.15,
  committed: 0.1,
  market: 0.1,
};

/** Build the factor set for a rec. Pass `margin: null` for an uncosted SKU — its
 *  margin factor is DROPPED (present:false), matching the graceful-degrade rule. */
function factors(vals: {
  urgency: number;
  margin: number | null;
  abc: number;
  priority: number;
  committed: number;
}): RankFactor[] {
  return [
    { key: 'urgency', weight: WEIGHTS.urgency, value: vals.urgency, present: true },
    {
      key: 'margin',
      weight: WEIGHTS.margin,
      value: vals.margin,
      present: vals.margin !== null,
    },
    { key: 'abc', weight: WEIGHTS.abc, value: vals.abc, present: true },
    { key: 'priority', weight: WEIGHTS.priority, value: vals.priority, present: true },
    { key: 'committed', weight: WEIGHTS.committed, value: vals.committed, present: true },
  ];
}

function supplier(
  code: string,
  name: string,
  cost: number | null,
  lead: number,
  score: number,
): SupplierChoice {
  return {
    supplier_code: code,
    supplier_name: name,
    unit_cost: cost,
    lead_time_days: lead,
    composite_score: score,
    is_primary: true,
  };
}

/** Shorthand seed for one buy rec — only the fields that vary across the set. */
interface Seed {
  rank: number;
  sku: string;
  product_name: string;
  abc_class: 'A' | 'B' | 'C';
  xyz_class: 'X' | 'Y' | 'Z';
  order_qty: number;
  unit_cost: number | null;
  /** null when uncosted (no supplier cost on file → margin dropped). */
  cash_impact: number | null;
  net_position: number;
  days_of_cover: number;
  days_to_stockout: number;
  reorder_point: number;
  supplier_name: string;
  supplier_code: string;
  lead_time_days: number;
  fac: {
    urgency: number;
    margin: number | null;
    abc: number;
    priority: number;
    committed: number;
  };
}

// Ranks 1..14 are pre-sorted by frozen rank_score (desc). cash_impact is tuned so
// that at DEFAULT_BUDGET the greedy allocator skips the big rank-6/8/13 items and
// still funds the small rank-9 item after them — the skip-overflow demo.
const SEEDS: Seed[] = [
  { rank: 1, sku: 'BRK-450', product_name: 'Brake Disc 450mm', abc_class: 'A', xyz_class: 'X', order_qty: 40, unit_cost: 80, cash_impact: 3_200, net_position: -12, days_of_cover: 3, days_to_stockout: 3, reorder_point: 60, supplier_name: 'Apex Auto Parts', supplier_code: 'SUP-APX', lead_time_days: 7, fac: { urgency: 0.98, margin: 0.62, abc: 1.0, priority: 0.8, committed: 0.7 } },
  { rank: 2, sku: 'SPK-010', product_name: 'Spark Plug 010', abc_class: 'A', xyz_class: 'X', order_qty: 300, unit_cost: null, cash_impact: null, net_position: -40, days_of_cover: 4, days_to_stockout: 4, reorder_point: 220, supplier_name: 'Volt Electricals', supplier_code: 'SUP-VLT', lead_time_days: 10, fac: { urgency: 0.95, margin: null, abc: 1.0, priority: 0.75, committed: 0.65 } },
  { rank: 3, sku: 'BRK-620', product_name: 'Brake Pad Set 620', abc_class: 'A', xyz_class: 'X', order_qty: 160, unit_cost: 80, cash_impact: 12_800, net_position: 8, days_of_cover: 5, days_to_stockout: 5, reorder_point: 150, supplier_name: 'Apex Auto Parts', supplier_code: 'SUP-APX', lead_time_days: 7, fac: { urgency: 0.9, margin: 0.7, abc: 1.0, priority: 0.7, committed: 0.6 } },
  { rank: 4, sku: 'FLT-120', product_name: 'Oil Filter 120', abc_class: 'B', xyz_class: 'Y', order_qty: 120, unit_cost: 20, cash_impact: 2_400, net_position: 15, days_of_cover: 7, days_to_stockout: 7, reorder_point: 90, supplier_name: 'FilterWorks', supplier_code: 'SUP-FLW', lead_time_days: 5, fac: { urgency: 0.82, margin: 0.55, abc: 0.6, priority: 0.6, committed: 0.55 } },
  { rank: 5, sku: 'HOS-330', product_name: 'Radiator Hose 330', abc_class: 'B', xyz_class: 'Y', order_qty: 200, unit_cost: null, cash_impact: null, net_position: 20, days_of_cover: 9, days_to_stockout: 9, reorder_point: 140, supplier_name: 'ThermoLine', supplier_code: 'SUP-THL', lead_time_days: 12, fac: { urgency: 0.78, margin: null, abc: 0.6, priority: 0.55, committed: 0.5 } },
  { rank: 6, sku: 'ALT-900', product_name: 'Alternator 90A', abc_class: 'A', xyz_class: 'Y', order_qty: 25, unit_cost: 260, cash_impact: 6_500, net_position: 6, days_of_cover: 11, days_to_stockout: 11, reorder_point: 30, supplier_name: 'Volt Electricals', supplier_code: 'SUP-VLT', lead_time_days: 14, fac: { urgency: 0.7, margin: 0.6, abc: 1.0, priority: 0.5, committed: 0.5 } },
  { rank: 7, sku: 'BLT-045', product_name: 'Timing Belt 045', abc_class: 'B', xyz_class: 'X', order_qty: 90, unit_cost: 20, cash_impact: 1_800, net_position: 30, days_of_cover: 12, days_to_stockout: 12, reorder_point: 110, supplier_name: 'DriveTrain Co', supplier_code: 'SUP-DTC', lead_time_days: 8, fac: { urgency: 0.66, margin: 0.5, abc: 0.6, priority: 0.5, committed: 0.5 } },
  { rank: 8, sku: 'PMP-210', product_name: 'Water Pump 210', abc_class: 'C', xyz_class: 'Y', order_qty: 60, unit_cost: 155, cash_impact: 9_300, net_position: 4, days_of_cover: 6, days_to_stockout: 6, reorder_point: 70, supplier_name: 'ThermoLine', supplier_code: 'SUP-THL', lead_time_days: 15, fac: { urgency: 0.85, margin: 0.2, abc: 0.3, priority: 0.35, committed: 0.4 } },
  { rank: 9, sku: 'GKT-088', product_name: 'Head Gasket 088', abc_class: 'C', xyz_class: 'Z', order_qty: 40, unit_cost: 30, cash_impact: 1_200, net_position: 12, days_of_cover: 14, days_to_stockout: 14, reorder_point: 55, supplier_name: 'SealPro', supplier_code: 'SUP-SLP', lead_time_days: 9, fac: { urgency: 0.6, margin: 0.45, abc: 0.3, priority: 0.45, committed: 0.45 } },
  { rank: 10, sku: 'CLT-500', product_name: 'Clutch Kit 500', abc_class: 'B', xyz_class: 'Y', order_qty: 20, unit_cost: 205, cash_impact: 4_100, net_position: 10, days_of_cover: 18, days_to_stockout: 18, reorder_point: 24, supplier_name: 'DriveTrain Co', supplier_code: 'SUP-DTC', lead_time_days: 11, fac: { urgency: 0.5, margin: 0.5, abc: 0.6, priority: 0.4, committed: 0.4 } },
  { rank: 11, sku: 'WPR-018', product_name: 'Wiper Blade 018', abc_class: 'C', xyz_class: 'Z', order_qty: 250, unit_cost: null, cash_impact: null, net_position: 40, days_of_cover: 20, days_to_stockout: 20, reorder_point: 180, supplier_name: 'ClearView', supplier_code: 'SUP-CLV', lead_time_days: 6, fac: { urgency: 0.48, margin: null, abc: 0.3, priority: 0.35, committed: 0.35 } },
  { rank: 12, sku: 'BAT-770', product_name: 'Battery 77Ah', abc_class: 'B', xyz_class: 'Y', order_qty: 30, unit_cost: 97, cash_impact: 2_900, net_position: 22, days_of_cover: 25, days_to_stockout: 25, reorder_point: 26, supplier_name: 'Volt Electricals', supplier_code: 'SUP-VLT', lead_time_days: 10, fac: { urgency: 0.42, margin: 0.48, abc: 0.6, priority: 0.35, committed: 0.35 } },
  { rank: 13, sku: 'SHK-340', product_name: 'Shock Absorber 340', abc_class: 'C', xyz_class: 'Z', order_qty: 40, unit_cost: 190, cash_impact: 7_600, net_position: 18, days_of_cover: 22, days_to_stockout: 22, reorder_point: 28, supplier_name: 'RideSoft', supplier_code: 'SUP-RDS', lead_time_days: 13, fac: { urgency: 0.4, margin: 0.35, abc: 0.3, priority: 0.3, committed: 0.35 } },
  { rank: 14, sku: 'BLB-002', product_name: 'Headlight Bulb H4', abc_class: 'C', xyz_class: 'Z', order_qty: 150, unit_cost: 6, cash_impact: 900, net_position: 35, days_of_cover: 40, days_to_stockout: 40, reorder_point: 90, supplier_name: 'ClearView', supplier_code: 'SUP-CLV', lead_time_days: 6, fac: { urgency: 0.3, margin: 0.4, abc: 0.3, priority: 0.3, committed: 0.3 } },
];

function buildRec(seed: Seed): ReorderRecommendation {
  const fac = factors(seed.fac);
  return {
    id: `rec-${seed.sku}`,
    type: 'buy',
    sku: seed.sku,
    product_name: seed.product_name,
    abc_class: seed.abc_class,
    xyz_class: seed.xyz_class,
    warehouse_code: 'WH-KL',
    warehouse_name: 'Kuala Lumpur DC',
    is_network: false,
    allocation: null,
    order_qty: seed.order_qty,
    recommended_qty: seed.order_qty,
    reorder_point: seed.reorder_point,
    min_qty: null,
    max_qty: null,
    order_up_to: null,
    net_position: seed.net_position,
    days_of_cover: seed.days_of_cover,
    reason: 'reorder_point',
    reason_label: 'net ≤ ROP',
    confidence: seed.xyz_class === 'X' ? 'high' : seed.xyz_class === 'Y' ? 'medium' : 'low',
    sample_size: seed.xyz_class === 'X' ? 24 : seed.xyz_class === 'Y' ? 12 : 5,
    supplier: supplier(
      seed.supplier_code,
      seed.supplier_name,
      seed.unit_cost,
      seed.lead_time_days,
      82,
    ),
    // A ranked alternative set for the M4 Slice B "switch supplier" flow — the
    // primary plus two deterministic alternatives (one pricier + slower, one
    // cheaper + slower) so the Adjust recompute preview is demonstrable.
    alternatives: [
      supplier(seed.supplier_code, seed.supplier_name, seed.unit_cost, seed.lead_time_days, 82),
      supplier(
        'SUP-GEN',
        'Generic Parts Co',
        seed.unit_cost === null ? null : Math.round(seed.unit_cost * 1.08),
        seed.lead_time_days + 3,
        74,
      ),
      supplier(
        'SUP-EAST',
        'Eastgate Trading',
        seed.unit_cost === null ? null : Math.round(seed.unit_cost * 0.92),
        seed.lead_time_days + 6,
        69,
      ),
    ].map((s) => ({ ...s, is_primary: s.supplier_code === seed.supplier_code })),
    is_exception: false,
    disposition_action: null,
    transfer_flag: null,
    forecast_daily_demand: seed.order_qty > 0 ? Math.max(1, Math.round(seed.reorder_point / 8)) : 0,
    lead_time_days: seed.lead_time_days,
    lead_time_source: 'measured',
    safety_stock: Math.round(seed.reorder_point * 0.2),
    safety_stock_method: 'statistical',
    safety_stock_fallback: null,
    service_level: 0.95,
    safety_days: null,
    review_days: 7,
    moq: null,
    order_multiple: null,
    policy_type: 'reorder_point',
    supplier_selection: 'primary',
    // M4 cash fields
    unit_cost: seed.unit_cost,
    cash_impact: seed.cash_impact,
    rank: seed.rank,
    rank_score: Number(scoreFromFactors(fac).toFixed(4)),
    funding_status: null,
    days_to_stockout: seed.days_to_stockout,
    rank_factors: fac,
  };
}

/** The frozen mock buy set, ordered by rank (1..N). Cloned per read so a
 *  component annotating `funding_status` never mutates the seed. */
export const MOCK_BUY_RECS: ReorderRecommendation[] = SEEDS.map(buildRec);

/** Σ cash_impact across all costed buy recs (uncosted contribute 0). */
export const TOTAL_BUY_CASH = totalCostedCash(MOCK_BUY_RECS);

/** Slider ceiling — Σ costed cash with ~10% headroom, rounded to RM 1,000. */
export const SLIDER_MAX = sliderMaxFor(MOCK_BUY_RECS);

/** Default budget — derived from the fixture's costed total; lands the funded
 *  boundary mid-list with a visible skip-overflow. */
export const DEFAULT_BUDGET = defaultBudgetFor(MOCK_BUY_RECS);
