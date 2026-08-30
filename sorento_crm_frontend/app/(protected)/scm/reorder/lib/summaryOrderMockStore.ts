/**
 * ============================================================================
 * SCM Purchasing and Fulfilment - SUMMARY ORDER REPORT MOCK STORE (Phase 1 only)
 * ============================================================================
 * Deterministic fixtures for the Summary Order Report (UAC Groups C2 + C3, and
 * Stage 2's Groups E + F), so the prototype can be walked with NO backend. Phase 2
 * flips `USE_SUMMARY_ORDER_MOCKS` to false and DELETES this file. Nothing else
 * imports it except its own tests.
 *
 * Every figure is shaped after the real database, not invented: product codes
 * (`B2155-NL-BLUE`, `SRTWT7408`, `SRTBS4832`), the `BRW` fulfilment pool and its
 * `BRW-IB` / `BRW-BB` bins, and the Chinese sanitary-ware suppliers whose costs
 * are quoted ex-works in CNY.
 *
 * The rows are chosen to make every state in the ACs reachable by clicking:
 *
 * - `B2155-NL-BLUE`  chosen 600 against a shortfall of 278. A chosen quantity
 *                      ABOVE the shortfall is the normal case, not a warning
 *                      (AC-C2.7). Carries BOTH a demand rate and dimensions, so
 *                      the consequence panel can state all five figures. Its
 *                      retail drill holds the 2-unit line that has waited 214
 *                      days, which outranks the 96-unit line raised in May
 *                      (AC-C2.4), and a supplier that has NEVER delivered it
 *                      while quoting the lowest cost (AC-C2.5). The only row with
 *                      UNCLASSIFIED demand, so that exception is reachable, and
 *                      the only one with a chosen quantity split back across two
 *                      locations (AC-F08).
 * - `SRTWT7408`      the first row of the first report anyone read: 4,397 in
 *                      the pool against 307 of demand, so nothing to buy. Has a
 *                      demand rate but NO recorded dimensions, so the volume
 *                      figure must name the missing input.
 * - `SRTBS4832`      the ADR-0011 case: net position +133 yet 67 short on a
 *                      date, because the PO of 200 lands 22 days late. Has
 *                      NEITHER a demand rate nor dimensions.
 * - `SRTSK2210`      last bought in 2021. Its only supplier is flagged stale,
 *                      which is what separates a fast mover from a dead line
 *                      (AC-C2.6), and its single retail line has waited 402 days.
 * - `SRTSH6120`      already decided, at exactly the engine's suggestion.
 * - `SRTAC0904`      nothing to decide and no supplier on file, so the empty
 *                      states are reachable.
 * - `SRTTB1120`      the AC-F11 worked case: 1 needed at BRW and 1 at JB, a
 *                      total unrounded need of 2 against a supplier multiple of
 *                      10, so the ONE product row rounds once to 10. Sold in `EA`
 *                      at 0 decimal places, so `2.5` is refused on it (AC-F12).
 * - `SRTAD9002`      the AC-F12 pair to it: sold in `kg` at 3 decimal places,
 *                      total need 2.5 and no supplier constraint, so the suggested
 *                      quantity is 2.5 and `2.5` is accepted.
 *
 * Deterministic by construction: no `Math.random`, no `Date.now`. Every
 * `days_outstanding` and `stale_days` is the whole-day count from its own date
 * to `AS_OF`, so a reader can check any of them by hand.
 *
 * ## Stage 2 scenarios
 *
 * Which of the six Stage-2 states this store serves is decided by the ONE constant
 * in `frontPlanningMockStore` (`DEFAULT_SCENARIO`), so this store and the PO
 * worklist can never disagree about the run they are describing. It is a
 * compile-time constant with no runtime selector - the Phase-1 `?plan_mock=` URL
 * switch is gone.
 * ============================================================================
 */
import { frontPlanningScenario, runGrainFields } from './frontPlanningMockStore';
import { decimalPlacesOf, exceedsPrecision, precisionError } from './qtyPrecision';
import type {
  OrderSummaryDecisionInput,
  OrderSummaryDecisionResult,
  OrderSummaryDemandDrill,
  OrderSummaryDemandKind,
  OrderSummaryLocationAllocation,
  OrderSummaryLocationRow,
  OrderSummaryLocations,
  OrderSummaryReport,
  OrderSummaryRow,
  OrderSummarySuppliers,
  ProjectDemandLine,
  UnclassifiedDemandLine,
} from '../types/summaryOrder.types';

/**
 * Phase-2: OFF. Every function below is unreachable from a screen; the service
 * calls the real `/api/v1/scm/order-summary` routes instead. The fixtures stay
 * because the vitest specs for the report, the drill, the decision sheet and the
 * service's own mock branch are written against them.
 */
export const USE_SUMMARY_ORDER_MOCKS = false;

/** The date every ageing figure below is counted to. */
export const AS_OF = '2026-08-03';

/** Opaque run key. Identifies the week; never rendered. */
export const MOCK_RUN_ID = 'run-2026-w32';

const GENERATED_AT = '2026-08-03T07:05:00';

/**
 * The Order summary tile's count: short products with no quantity decided yet.
 * A constant here rather than a query on the plan page, so opening the plan does
 * not fetch a whole report just to put a number on a card. Phase 2 feeds it from
 * the run summary, alongside `MOCK_PLAN_TILE_COUNTS`.
 */
export const MOCK_ORDER_SUMMARY_PENDING = 2;

/** How old a last PO date has to be before it is flagged stale (AC-C2.6). */
const STALE_AFTER_DAYS = 365;

// ── rows ────────────────────────────────────────────────────────────────────

const ROWS: OrderSummaryRow[] = [
  {
    product_code: 'B2155-NL-BLUE',
    product_name: 'Basin 2155 Nano-Lite Blue',
    uom: 'PCS',
    on_hand: 96,
    project_demand: 480,
    retail_outstanding: 186,
    unclassified_demand_qty: 12,
    qty_on_order: 120,
    qty_in_transit: 200,
    shortfall: 278,
    // 180 firm Project Buy + 80 netted Retail = 260 raw, rounded ONCE to the
    // supplier's multiple of 50 (AC-E06 / AC-F11). Not 4 separate roundings.
    suggested_qty: 300,
    project_buy_qty: 180,
    retail_replenishment_qty: 80,
    earliest_project_need_date: '2026-09-15',
    uom_decimal_places: 0,
    location_allocations: [
      { warehouse_code: 'BRW', warehouse_name: 'Bandar Baru Warehouse', allocated_qty: 400 },
      { warehouse_code: 'JB', warehouse_name: 'Johor Bahru Branch', allocated_qty: 200 },
    ],
    chosen_qty: 600,
    chosen_supplier_code: 'GDS',
    chosen_supplier_name: 'Guangdong Sanitary Ware',
    decided_by: 'Loo Keng Hoe',
    decided_at: '2026-08-03T09:41:00',
    avg_daily_demand: 3.6,
    unit_volume_cbm: 0.082,
    spare_lands_at: 'BRW',
    project_demand_line_count: 3,
    retail_outstanding_line_count: 4,
    unclassified_line_count: 1,
    max_days_outstanding: 214,
  },
  {
    product_code: 'SRTWT7408',
    product_name: 'Wall-hung WC 7408',
    uom: 'PCS',
    on_hand: 4397,
    project_demand: 307,
    retail_outstanding: 0,
    unclassified_demand_qty: 0,
    qty_on_order: 0,
    qty_in_transit: 0,
    shortfall: 0,
    suggested_qty: 0,
    // Every project line is covered by a confirmed Reserve, so nothing is Buy.
    project_buy_qty: 0,
    retail_replenishment_qty: 0,
    earliest_project_need_date: null,
    uom_decimal_places: 0,
    location_allocations: null,
    chosen_qty: null,
    chosen_supplier_code: null,
    chosen_supplier_name: null,
    decided_by: null,
    decided_at: null,
    avg_daily_demand: 8.2,
    // No dimensions on file, which is the majority case across the book.
    unit_volume_cbm: null,
    spare_lands_at: 'BRW',
    project_demand_line_count: 2,
    retail_outstanding_line_count: 0,
    unclassified_line_count: 0,
    max_days_outstanding: null,
  },
  {
    product_code: 'SRTBS4832',
    product_name: 'Basin mixer 4832',
    uom: 'PCS',
    on_hand: 140,
    project_demand: 207,
    retail_outstanding: 0,
    unclassified_demand_qty: 0,
    qty_on_order: 200,
    qty_in_transit: 0,
    // Net position is +133 and the item is still 67 short, because the PO of 200
    // lands 25 Aug against an order due 3 Aug. The dated engine, not on-hand maths.
    shortfall: 67,
    suggested_qty: 100,
    project_buy_qty: 100,
    retail_replenishment_qty: 0,
    earliest_project_need_date: '2026-08-03',
    uom_decimal_places: 0,
    location_allocations: null,
    chosen_qty: null,
    chosen_supplier_code: null,
    chosen_supplier_name: null,
    decided_by: null,
    decided_at: null,
    avg_daily_demand: null,
    unit_volume_cbm: null,
    spare_lands_at: 'BRW',
    project_demand_line_count: 2,
    retail_outstanding_line_count: 0,
    unclassified_line_count: 0,
    max_days_outstanding: null,
  },
  {
    product_code: 'SRTSK2210',
    product_name: 'Kitchen sink 2210',
    uom: 'PCS',
    on_hand: 12,
    project_demand: 0,
    retail_outstanding: 8,
    unclassified_demand_qty: 0,
    qty_on_order: 0,
    qty_in_transit: 0,
    shortfall: 8,
    // Rounded up to the supplier's minimum order of 50.
    suggested_qty: 50,
    project_buy_qty: 0,
    retail_replenishment_qty: 8,
    earliest_project_need_date: null,
    uom_decimal_places: 0,
    location_allocations: null,
    chosen_qty: null,
    chosen_supplier_code: null,
    chosen_supplier_name: null,
    decided_by: null,
    decided_at: null,
    avg_daily_demand: 0.04,
    unit_volume_cbm: 0.145,
    spare_lands_at: 'BRW-IB',
    project_demand_line_count: 0,
    retail_outstanding_line_count: 1,
    unclassified_line_count: 0,
    max_days_outstanding: 402,
  },
  {
    product_code: 'SRTSH6120',
    product_name: 'Shower set 6120',
    uom: 'SET',
    on_hand: 0,
    project_demand: 140,
    retail_outstanding: 35,
    unclassified_demand_qty: 0,
    qty_on_order: 90,
    qty_in_transit: 60,
    shortfall: 25,
    suggested_qty: 40,
    project_buy_qty: 30,
    retail_replenishment_qty: 10,
    earliest_project_need_date: '2026-08-19',
    uom_decimal_places: 0,
    location_allocations: [
      { warehouse_code: 'BRW', warehouse_name: 'Bandar Baru Warehouse', allocated_qty: 30 },
      { warehouse_code: 'IPH', warehouse_name: 'Ipoh Branch', allocated_qty: 10 },
    ],
    chosen_qty: 40,
    chosen_supplier_code: 'FSC',
    chosen_supplier_name: 'Foshan Ceramics',
    decided_by: 'Loo Keng Hoe',
    decided_at: '2026-08-03T09:52:00',
    avg_daily_demand: 1.8,
    unit_volume_cbm: 0.21,
    spare_lands_at: 'BRW',
    project_demand_line_count: 2,
    retail_outstanding_line_count: 2,
    unclassified_line_count: 0,
    max_days_outstanding: 47,
  },
  {
    product_code: 'SRTAC0904',
    product_name: 'Accessory pack 0904',
    uom: 'PCS',
    on_hand: 1240,
    project_demand: 0,
    retail_outstanding: 0,
    unclassified_demand_qty: 0,
    qty_on_order: 0,
    qty_in_transit: 0,
    shortfall: 0,
    suggested_qty: 0,
    project_buy_qty: 0,
    retail_replenishment_qty: 0,
    earliest_project_need_date: null,
    uom_decimal_places: 0,
    location_allocations: null,
    chosen_qty: null,
    chosen_supplier_code: null,
    chosen_supplier_name: null,
    decided_by: null,
    decided_at: null,
    avg_daily_demand: null,
    unit_volume_cbm: 0.006,
    spare_lands_at: 'BRW',
    project_demand_line_count: 0,
    retail_outstanding_line_count: 0,
    unclassified_line_count: 0,
    max_days_outstanding: null,
  },
  {
    // AC-F11, worked: 1 at BRW + 1 at JB is a total unrounded need of 2, and the
    // supplier ships in tens, so the ONE product row rounds once to 10. Rounding
    // each location first would have bought 20.
    product_code: 'SRTTB1120',
    product_name: 'Towel bar 1120',
    uom: 'EA',
    on_hand: 3,
    project_demand: 1,
    retail_outstanding: 1,
    unclassified_demand_qty: 0,
    qty_on_order: 0,
    qty_in_transit: 0,
    shortfall: 2,
    suggested_qty: 10,
    project_buy_qty: 1,
    retail_replenishment_qty: 1,
    earliest_project_need_date: '2026-09-02',
    // Counted in whole units, so 2.5 is refused on this row (AC-F12).
    uom_decimal_places: 0,
    location_allocations: null,
    chosen_qty: null,
    chosen_supplier_code: null,
    chosen_supplier_name: null,
    decided_by: null,
    decided_at: null,
    avg_daily_demand: 0.12,
    unit_volume_cbm: 0.004,
    spare_lands_at: 'BRW',
    project_demand_line_count: 1,
    retail_outstanding_line_count: 1,
    unclassified_line_count: 0,
    max_days_outstanding: 21,
  },
  {
    // AC-F12, the other half of the pair: a measure unit at 3 decimal places, no
    // supplier constraint, total need 2.5 - so the suggestion IS 2.5, and 2.5 is
    // an accepted quantity here where it is refused on the `EA` row above.
    product_code: 'SRTAD9002',
    product_name: 'Adhesive sealant 9002',
    uom: 'kg',
    on_hand: 0.75,
    project_demand: 1.25,
    retail_outstanding: 1.25,
    unclassified_demand_qty: 0,
    qty_on_order: 0,
    qty_in_transit: 0,
    shortfall: 2.5,
    suggested_qty: 2.5,
    project_buy_qty: 1.25,
    retail_replenishment_qty: 1.25,
    earliest_project_need_date: '2026-08-28',
    uom_decimal_places: 3,
    location_allocations: null,
    chosen_qty: null,
    chosen_supplier_code: null,
    chosen_supplier_name: null,
    decided_by: null,
    decided_at: null,
    avg_daily_demand: 0.08,
    unit_volume_cbm: null,
    spare_lands_at: 'BRW',
    project_demand_line_count: 1,
    retail_outstanding_line_count: 1,
    unclassified_line_count: 0,
    max_days_outstanding: 9,
  },
];

// ── member locations ────────────────────────────────────────────────────────

/**
 * The locations behind each product row (AC-F08).
 *
 * Demand is split by channel; supply is NOT. `on_hand`, `incoming_spo`,
 * `on_order_po` and `reorder_level` are single shared facts of the
 * product-location and appear once, which is the whole point of keeping channel
 * as a demand breakdown rather than a row key (AC-F07).
 */
const LOCATIONS: Record<string, OrderSummaryLocationRow[]> = {
  'B2155-NL-BLUE': [
    {
      warehouse_code: 'BRW',
      warehouse_name: 'Bandar Baru Warehouse',
      project_need: 120,
      retail_need: 55,
      on_hand: 60,
      incoming_spo: 200,
      on_order_po: 120,
      reorder_level: 80,
      avg_daily_demand: 2.1,
      allocated_qty: 400,
    },
    {
      warehouse_code: 'JB',
      warehouse_name: 'Johor Bahru Branch',
      project_need: 60,
      retail_need: 25,
      on_hand: 36,
      incoming_spo: 0,
      on_order_po: 0,
      reorder_level: 40,
      avg_daily_demand: 1.5,
      allocated_qty: 200,
    },
  ],
  SRTWT7408: [
    {
      warehouse_code: 'BRW',
      warehouse_name: 'Bandar Baru Warehouse',
      project_need: 0,
      retail_need: 0,
      on_hand: 4397,
      incoming_spo: 0,
      on_order_po: 0,
      reorder_level: 500,
      avg_daily_demand: 8.2,
      allocated_qty: null,
    },
  ],
  SRTBS4832: [
    {
      warehouse_code: 'BRW',
      warehouse_name: 'Bandar Baru Warehouse',
      project_need: 100,
      retail_need: 0,
      on_hand: 140,
      incoming_spo: 0,
      on_order_po: 200,
      reorder_level: 60,
      avg_daily_demand: null,
      allocated_qty: null,
    },
  ],
  SRTSK2210: [
    {
      warehouse_code: 'BRW-IB',
      warehouse_name: 'Bandar Baru Inbound Bin',
      project_need: 0,
      retail_need: 8,
      on_hand: 12,
      incoming_spo: 0,
      on_order_po: 0,
      // Nobody has set one here, which is not the same fact as zero.
      reorder_level: null,
      avg_daily_demand: 0.04,
      allocated_qty: null,
    },
  ],
  SRTSH6120: [
    {
      warehouse_code: 'BRW',
      warehouse_name: 'Bandar Baru Warehouse',
      project_need: 30,
      retail_need: 5,
      on_hand: 0,
      incoming_spo: 60,
      on_order_po: 90,
      reorder_level: 20,
      avg_daily_demand: 1.2,
      allocated_qty: 30,
    },
    {
      warehouse_code: 'IPH',
      warehouse_name: 'Ipoh Branch',
      project_need: 0,
      retail_need: 5,
      on_hand: 0,
      incoming_spo: 0,
      on_order_po: 0,
      reorder_level: 10,
      avg_daily_demand: 0.6,
      allocated_qty: 10,
    },
  ],
  SRTTB1120: [
    {
      warehouse_code: 'BRW',
      warehouse_name: 'Bandar Baru Warehouse',
      project_need: 1,
      retail_need: 0,
      on_hand: 2,
      incoming_spo: 0,
      on_order_po: 0,
      reorder_level: 2,
      avg_daily_demand: 0.07,
      allocated_qty: null,
    },
    {
      warehouse_code: 'JB',
      warehouse_name: 'Johor Bahru Branch',
      project_need: 0,
      retail_need: 1,
      on_hand: 1,
      incoming_spo: 0,
      on_order_po: 0,
      reorder_level: 1,
      avg_daily_demand: 0.05,
      allocated_qty: null,
    },
  ],
  SRTAD9002: [
    {
      warehouse_code: 'BRW',
      warehouse_name: 'Bandar Baru Warehouse',
      project_need: 1.25,
      retail_need: 0,
      on_hand: 0.75,
      incoming_spo: 0,
      on_order_po: 0,
      reorder_level: 1,
      avg_daily_demand: 0.05,
      allocated_qty: null,
    },
    {
      warehouse_code: 'JB',
      warehouse_name: 'Johor Bahru Branch',
      project_need: 0,
      retail_need: 1.25,
      on_hand: 0,
      incoming_spo: 0,
      on_order_po: 0,
      reorder_level: null,
      avg_daily_demand: 0.03,
      allocated_qty: null,
    },
  ],
  SRTAC0904: [
    {
      warehouse_code: 'BRW',
      warehouse_name: 'Bandar Baru Warehouse',
      project_need: 0,
      retail_need: 0,
      on_hand: 1240,
      incoming_spo: 0,
      on_order_po: 0,
      reorder_level: 100,
      avg_daily_demand: null,
      allocated_qty: null,
    },
  ],
};

// ── demand drills ───────────────────────────────────────────────────────────

/**
 * Project lines, ordered by required date. Sums match the row aggregate.
 *
 * `decision_ref` is the human trace from a Buy back to the CS decision that
 * confirmed it (AC-D06): a revision and an inquiry number, never a UUID. A line
 * whose SO has no confirmed decision carries null and is counted through the
 * legacy sheet leg instead.
 */
const PROJECT_LINES: Record<string, ProjectDemandLine[]> = {
  'B2155-NL-BLUE': [
    {
      project_name: 'Maryam Tuju Residence',
      so_number: 'SO-2026-0311',
      qty: 260,
      required_date: '2026-09-15',
      line_no: 10,
      warehouse_code: 'BRW',
      decision_ref: 'Rev 2 / INQ-2026-0188',
    },
    {
      project_name: 'Setia Mutiara City',
      so_number: 'SO-2026-0342',
      qty: 140,
      required_date: '2026-10-02',
      line_no: 20,
      warehouse_code: 'BRW',
      decision_ref: 'Rev 1 / INQ-2026-0201',
    },
    {
      project_name: 'Bandar Baru Development',
      so_number: 'SO-2026-0357',
      qty: 80,
      required_date: '2026-11-20',
      line_no: 30,
      warehouse_code: 'JB',
      decision_ref: null,
    },
  ],
  SRTWT7408: [
    {
      project_name: 'Bandar Baru Development',
      so_number: 'SO-2026-0357',
      qty: 67,
      required_date: '2026-08-14',
      line_no: 10,
      warehouse_code: 'BRW',
      decision_ref: 'Rev 1 / INQ-2026-0177',
    },
    {
      project_name: 'Setia Mutiara City',
      so_number: 'SO-2026-0361',
      qty: 240,
      required_date: '2026-09-30',
      line_no: 20,
      warehouse_code: 'BRW',
      decision_ref: 'Rev 1 / INQ-2026-0179',
    },
  ],
  SRTBS4832: [
    {
      project_name: 'Maryam Tuju Residence',
      so_number: 'SO-2026-0311',
      qty: 135,
      required_date: '2026-07-01',
      line_no: 40,
      warehouse_code: 'BRW',
      decision_ref: 'Rev 2 / INQ-2026-0188',
    },
    {
      project_name: 'Maryam Tuju Residence',
      so_number: 'SO-2026-0342',
      qty: 72,
      required_date: '2026-08-03',
      line_no: 50,
      warehouse_code: 'BRW',
      decision_ref: 'Rev 1 / INQ-2026-0201',
    },
  ],
  SRTSH6120: [
    {
      project_name: 'Ipoh Riverside',
      so_number: 'SO-2026-0349',
      qty: 60,
      required_date: '2026-08-19',
      line_no: 10,
      warehouse_code: 'IPH',
      decision_ref: 'Rev 1 / INQ-2026-0192',
    },
    {
      project_name: 'Ipoh Riverside',
      so_number: 'SO-2026-0372',
      qty: 80,
      required_date: '2026-10-15',
      line_no: 20,
      warehouse_code: 'BRW',
      decision_ref: 'Rev 1 / INQ-2026-0210',
    },
  ],
  SRTTB1120: [
    {
      project_name: 'Setia Mutiara City',
      so_number: 'SO-2026-0361',
      qty: 1,
      required_date: '2026-09-02',
      line_no: 60,
      warehouse_code: 'BRW',
      decision_ref: 'Rev 1 / INQ-2026-0179',
    },
  ],
  SRTAD9002: [
    {
      project_name: 'Ipoh Riverside',
      so_number: 'SO-2026-0372',
      qty: 1.25,
      required_date: '2026-08-28',
      line_no: 70,
      warehouse_code: 'BRW',
      decision_ref: 'Rev 1 / INQ-2026-0210',
    },
  ],
};

/**
 * Retail lines, WORST-FIRST by days outstanding (AC-C2.4). The order is the
 * server's, not the client's: the 2-unit line that has waited 214 days sits
 * above the 96-unit line raised in May, which is the whole point of the column.
 */
const RETAIL_LINES: Record<string, OrderSummaryDemandDrill['retail_lines']> = {
  'B2155-NL-BLUE': [
    {
      dealer_name: 'Kedai Perabot Seri Muda',
      so_number: 'SO-2025-1188',
      qty: 2,
      days_outstanding: 214,
      ordered_date: '2026-01-01',
    },
    {
      dealer_name: 'Hup Seng Hardware',
      so_number: 'SO-2026-0207',
      qty: 96,
      days_outstanding: 91,
      ordered_date: '2026-05-04',
    },
    {
      dealer_name: 'Lim Brothers Trading',
      so_number: 'SO-2026-0288',
      qty: 76,
      days_outstanding: 33,
      ordered_date: '2026-07-01',
    },
    {
      dealer_name: 'Bina Jaya Sanitary',
      so_number: 'SO-2026-0331',
      qty: 12,
      days_outstanding: 8,
      ordered_date: '2026-07-26',
    },
  ],
  SRTSK2210: [
    {
      dealer_name: 'Teik Seng Trading',
      so_number: 'SO-2025-0642',
      qty: 8,
      days_outstanding: 402,
      ordered_date: '2025-06-27',
    },
  ],
  SRTSH6120: [
    {
      dealer_name: 'Hup Seng Hardware',
      so_number: 'SO-2026-0264',
      qty: 20,
      days_outstanding: 47,
      ordered_date: '2026-06-17',
    },
    {
      dealer_name: 'Bina Jaya Sanitary',
      so_number: 'SO-2026-0322',
      qty: 15,
      days_outstanding: 12,
      ordered_date: '2026-07-22',
    },
  ],
  SRTTB1120: [
    {
      dealer_name: 'Lim Brothers Trading',
      so_number: 'SO-2026-0318',
      qty: 1,
      days_outstanding: 21,
      ordered_date: '2026-07-13',
    },
  ],
  SRTAD9002: [
    {
      dealer_name: 'Hup Seng Hardware',
      so_number: 'SO-2026-0334',
      qty: 1.25,
      days_outstanding: 9,
      ordered_date: '2026-07-25',
    },
  ],
};

/**
 * Demand whose SO carries no persisted `demand_class` (AC-E02).
 *
 * It stays visible as an exception and is excluded from the actionable
 * suggestion; it never becomes a third demand class and is never guessed at from
 * the fulfilment location.
 */
const UNCLASSIFIED_LINES: Record<string, UnclassifiedDemandLine[]> = {
  'B2155-NL-BLUE': [
    {
      customer_name: 'Sinaran Trading (imported 12 Jul)',
      so_number: 'SO-2026-0299',
      line_no: 10,
      qty: 12,
      ordered_date: '2026-07-12',
      exception: 'No demand class: the import stated no order type and the customer has no market segment',
    },
  ],
};

// ── supplier candidates ─────────────────────────────────────────────────────

/**
 * Costs are ex-works in the supplier's own currency (AC-C3.4). `cost_variance`
 * is incoming minus ordered, so a positive figure is a supplier that repriced
 * after we committed (AC-C3.3).
 */
const SUPPLIERS: Record<string, OrderSummarySuppliers['candidates']> = {
  'B2155-NL-BLUE': [
    {
      supplier_code: 'GDS',
      supplier_name: 'Guangdong Sanitary Ware',
      currency: 'CNY',
      last_po_cost: 128.4,
      last_po_date: '2026-06-12',
      last_po_number: 'PO-2026-0442',
      last_incoming_cost: 134.9,
      last_incoming_currency: 'CNY',
      last_incoming_date: '2026-07-28',
      cost_variance: 6.5,
      on_time_rate: 0.86,
      lead_time_days: 52,
      delivered_line_count: 37,
      is_stale: false,
      stale_days: 52,
      moq: 200,
      order_multiple: 50,
    },
    {
      supplier_code: 'FSC',
      supplier_name: 'Foshan Ceramics',
      currency: 'CNY',
      last_po_cost: 121.0,
      last_po_date: '2025-09-08',
      last_po_number: 'PO-2025-0913',
      last_incoming_cost: 119.5,
      last_incoming_currency: 'CNY',
      last_incoming_date: '2025-12-02',
      cost_variance: -1.5,
      on_time_rate: 0.62,
      lead_time_days: 68,
      delivered_line_count: 9,
      is_stale: false,
      stale_days: 329,
      moq: 100,
      order_multiple: 25,
    },
    {
      // Cheapest on paper and has never delivered this item. Said plainly, or the
      // number alone makes them look like the obvious pick (AC-C2.5).
      supplier_code: 'ZQH',
      supplier_name: 'Zhaoqing Homeware',
      currency: 'CNY',
      last_po_cost: 112.75,
      last_po_date: '2026-02-19',
      last_po_number: 'PO-2026-0118',
      last_incoming_cost: null,
      last_incoming_currency: null,
      last_incoming_date: null,
      cost_variance: null,
      on_time_rate: null,
      lead_time_days: 60,
      delivered_line_count: 0,
      is_stale: false,
      stale_days: 165,
      moq: 300,
      order_multiple: 100,
    },
  ],
  SRTWT7408: [
    {
      supplier_code: 'GDS',
      supplier_name: 'Guangdong Sanitary Ware',
      currency: 'CNY',
      last_po_cost: 402.0,
      last_po_date: '2026-04-30',
      last_po_number: 'PO-2026-0308',
      last_incoming_cost: 402.0,
      last_incoming_currency: 'CNY',
      last_incoming_date: '2026-06-21',
      cost_variance: 0,
      on_time_rate: 0.91,
      lead_time_days: 48,
      delivered_line_count: 64,
      is_stale: false,
      stale_days: 95,
      moq: 100,
      order_multiple: 20,
    },
  ],
  SRTBS4832: [
    {
      supplier_code: 'GDS',
      supplier_name: 'Guangdong Sanitary Ware',
      currency: 'CNY',
      last_po_cost: 96.2,
      last_po_date: '2026-05-22',
      last_po_number: 'PO-2026-0361',
      last_incoming_cost: 101.8,
      last_incoming_currency: 'CNY',
      last_incoming_date: '2026-07-14',
      cost_variance: 5.6,
      on_time_rate: 0.79,
      lead_time_days: 55,
      delivered_line_count: 22,
      is_stale: false,
      stale_days: 73,
      moq: 100,
      order_multiple: 25,
    },
  ],
  SRTSK2210: [
    {
      // Last bought in 2021. The flag is the answer to "is this line still alive".
      supplier_code: 'IPM',
      supplier_name: 'Ipoh Metalworks',
      currency: 'MYR',
      last_po_cost: 88.0,
      last_po_date: '2021-11-18',
      last_po_number: 'PO-2021-0207',
      last_incoming_cost: 88.0,
      last_incoming_currency: 'MYR',
      last_incoming_date: '2021-12-09',
      cost_variance: 0,
      on_time_rate: 1,
      lead_time_days: 21,
      delivered_line_count: 3,
      is_stale: true,
      stale_days: 1719,
      moq: 50,
      order_multiple: 10,
    },
  ],
  SRTSH6120: [
    {
      supplier_code: 'FSC',
      supplier_name: 'Foshan Ceramics',
      currency: 'CNY',
      last_po_cost: 214.5,
      last_po_date: '2026-07-09',
      last_po_number: 'PO-2026-0471',
      last_incoming_cost: 209.0,
      last_incoming_currency: 'CNY',
      last_incoming_date: '2026-07-30',
      cost_variance: -5.5,
      on_time_rate: 0.74,
      lead_time_days: 61,
      delivered_line_count: 14,
      is_stale: false,
      stale_days: 25,
      moq: 40,
      order_multiple: 10,
    },
    {
      supplier_code: 'GDS',
      supplier_name: 'Guangdong Sanitary Ware',
      currency: 'CNY',
      last_po_cost: 228.0,
      last_po_date: '2026-03-04',
      last_po_number: 'PO-2026-0164',
      last_incoming_cost: 231.4,
      last_incoming_currency: 'CNY',
      last_incoming_date: '2026-05-18',
      cost_variance: 3.4,
      on_time_rate: 0.88,
      lead_time_days: 50,
      delivered_line_count: 6,
      is_stale: false,
      stale_days: 152,
      moq: 100,
      order_multiple: 25,
    },
  ],
  SRTTB1120: [
    {
      // Ships in tens and sets no minimum, which is what makes the AC-F11 case
      // readable: the rounding on this row is the multiple alone.
      supplier_code: 'ZQH',
      supplier_name: 'Zhaoqing Homeware',
      currency: 'CNY',
      last_po_cost: 18.4,
      last_po_date: '2026-06-30',
      last_po_number: 'PO-2026-0455',
      last_incoming_cost: 18.4,
      // Same currency as the order, which is what lets `cost_variance` be a number at
      // all: the two sides are only subtractable when they are quoted in one money.
      last_incoming_currency: 'CNY',
      last_incoming_date: '2026-07-22',
      cost_variance: 0,
      on_time_rate: 0.93,
      lead_time_days: 40,
      delivered_line_count: 11,
      is_stale: false,
      stale_days: 34,
      moq: null,
      order_multiple: 10,
    },
  ],
  SRTAD9002: [
    {
      // No minimum and no multiple, so a 2.5 kg need stays a 2.5 kg suggestion.
      supplier_code: 'IPM',
      supplier_name: 'Ipoh Metalworks',
      currency: 'MYR',
      last_po_cost: 42.0,
      last_po_date: '2026-07-02',
      last_po_number: 'PO-2026-0463',
      last_incoming_cost: 42.0,
      last_incoming_currency: 'MYR',
      last_incoming_date: '2026-07-19',
      cost_variance: 0,
      on_time_rate: 0.97,
      lead_time_days: 14,
      delivered_line_count: 8,
      is_stale: false,
      stale_days: 32,
      moq: null,
      order_multiple: null,
    },
  ],
  // No supplier on file at all, so the candidate empty state is reachable.
  SRTAC0904: [],
};

// ── scenario shaping ────────────────────────────────────────────────────────

/**
 * A legacy run's row: the channel breakdown is UNAVAILABLE, not zero (AC-F10).
 *
 * Nulls are what the screen renders "Unavailable" from. Zeroing them would claim
 * the run was calculated with no Project demand, which is a different statement
 * and one nobody made.
 */
function toLegacyRow(row: OrderSummaryRow): OrderSummaryRow {
  return {
    ...row,
    unclassified_demand_qty: null,
    project_buy_qty: null,
    retail_replenishment_qty: null,
    earliest_project_need_date: null,
    uom_decimal_places: null,
    location_allocations: null,
    unclassified_line_count: 0,
  };
}

function scenarioRows(): OrderSummaryRow[] {
  const scenario = frontPlanningScenario();
  if (scenario === 'empty') return [];
  const rows = ROWS.map((r) => applyDecisions({ ...r }));
  return scenario === 'legacy' ? rows.map(toLegacyRow) : rows;
}

function scenarioLocations(productCode: string): OrderSummaryLocationRow[] {
  const rows = (LOCATIONS[productCode] ?? []).map((l) => ({ ...l }));
  if (frontPlanningScenario() !== 'legacy') return rows;
  return rows.map((l) => ({
    ...l,
    project_need: null,
    retail_need: null,
    allocated_qty: null,
  }));
}

// ── decisions taken during the walkthrough ──────────────────────────────────

/**
 * Decisions recorded in this browser session, so the prototype behaves like the
 * real thing: save a quantity, close the sheet, and the row shows it. Dies with
 * the tab, which is the honest limit of a Phase-1 mock.
 */
const sessionDecisions = new Map<string, OrderSummaryDecisionResult>();

/** Drop every session decision. Used by tests to keep fixtures independent. */
export function resetMockDecisions(): void {
  sessionDecisions.clear();
}

function applyDecisions(row: OrderSummaryRow): OrderSummaryRow {
  const decided = sessionDecisions.get(row.product_code);
  if (!decided) return row;
  return {
    ...row,
    chosen_qty: decided.chosen_qty,
    chosen_supplier_code: decided.chosen_supplier_code,
    chosen_supplier_name: decided.chosen_supplier_name,
    decided_by: decided.decided_by,
    decided_at: decided.decided_at,
    location_allocations: decided.location_allocations,
  };
}

/**
 * The chosen quantity split back to the frozen location needs (AC-F12).
 *
 * The real allocator works in the UOM's integer minor units and settles the
 * remainder by largest fraction, so the children sum EXACTLY to the parent with
 * no rescaling formula. This does the same arithmetic on the same inputs, which
 * is what makes the split in the prototype checkable by hand.
 */
function splitAcrossLocations(
  chosenQty: number,
  locations: OrderSummaryLocationRow[],
  dp: number,
): OrderSummaryLocationAllocation[] {
  if (locations.length === 0) return [];
  const scale = 10 ** dp;
  const total = Math.round(chosenQty * scale);
  const weights = locations.map(
    (l) => (l.project_need ?? 0) + (l.retail_need ?? 0) || 0,
  );
  const weightTotal = weights.reduce((t, w) => t + w, 0);
  // Nothing needs it anywhere: the whole quantity lands on the first location
  // rather than being spread on a weight that does not exist.
  const shares = weightTotal === 0
    ? locations.map((_, i) => (i === 0 ? total : 0))
    : weights.map((w) => (total * w) / weightTotal);
  const floors = shares.map((s) => Math.floor(s));
  let remainder = total - floors.reduce((t, f) => t + f, 0);
  const order = shares
    .map((s, i) => ({ i, frac: s - Math.floor(s) }))
    .sort((a, b) => b.frac - a.frac || a.i - b.i);
  const minor = [...floors];
  for (const { i } of order) {
    if (remainder <= 0) break;
    minor[i] += 1;
    remainder -= 1;
  }
  return locations.map((l, i) => ({
    warehouse_code: l.warehouse_code,
    warehouse_name: l.warehouse_name,
    allocated_qty: minor[i] / scale,
  }));
}

// ── named fixtures ──────────────────────────────────────────────────────────

/** Named fixtures, exported so the component tests assert the SAME figures. */
export const SUMMARY_ORDER_FIXTURES = {
  report: (): OrderSummaryReport => ({
    run_id: MOCK_RUN_ID,
    as_of: AS_OF,
    generated_at: GENERATED_AT,
    decision_grain: 'product',
    is_legacy: false,
    rows: ROWS.map((r) => ({ ...r })),
  }),
  /** A run with nothing to decide, for the empty state. */
  emptyReport: (): OrderSummaryReport => ({
    run_id: MOCK_RUN_ID,
    as_of: AS_OF,
    generated_at: GENERATED_AT,
    decision_grain: 'product',
    is_legacy: false,
    rows: [],
  }),
  /** A run created before the front-planning contract: no breakdown, no decisions. */
  legacyReport: (): OrderSummaryReport => ({
    run_id: MOCK_RUN_ID,
    as_of: AS_OF,
    generated_at: GENERATED_AT,
    decision_grain: null,
    is_legacy: true,
    rows: ROWS.map((r) => toLegacyRow({ ...r })),
  }),
  /** A run whose decisions are owned by the per-location grain (AC-F02). */
  locationGrainReport: (): OrderSummaryReport => ({
    run_id: MOCK_RUN_ID,
    as_of: AS_OF,
    generated_at: GENERATED_AT,
    decision_grain: 'location',
    is_legacy: false,
    rows: ROWS.map((r) => ({ ...r })),
  }),
  row: (productCode: string): OrderSummaryRow => {
    const found = ROWS.find((r) => r.product_code === productCode);
    if (!found) throw new Error(`No mock row for ${productCode}`);
    return { ...found };
  },
  demand: (productCode: string, kind: OrderSummaryDemandKind): OrderSummaryDemandDrill =>
    buildDrill(productCode, kind),
  locations: (productCode: string): OrderSummaryLocations => buildLocations(productCode),
  suppliers: (productCode: string): OrderSummarySuppliers => ({
    product_code: productCode,
    stale_after_days: STALE_AFTER_DAYS,
    candidates: (SUPPLIERS[productCode] ?? []).map((c) => ({ ...c })),
  }),
};

/** `dealer` is the legacy name of `retail` and reads the same lines. */
function isRetailKind(kind: OrderSummaryDemandKind): boolean {
  return kind === 'retail' || kind === 'dealer';
}

function buildDrill(
  productCode: string,
  kind: OrderSummaryDemandKind,
): OrderSummaryDemandDrill {
  const projectLines = kind === 'project' ? (PROJECT_LINES[productCode] ?? []) : [];
  const retailLines = isRetailKind(kind) ? (RETAIL_LINES[productCode] ?? []) : [];
  const unclassifiedLines =
    kind === 'unclassified' ? (UNCLASSIFIED_LINES[productCode] ?? []) : [];
  const sum = (qty: number, line: { qty: number }) => qty + line.qty;
  const total =
    projectLines.reduce(sum, 0) + retailLines.reduce(sum, 0) + unclassifiedLines.reduce(sum, 0);
  return {
    product_code: productCode,
    kind,
    total_qty: total,
    project_lines: projectLines.map((l) => ({ ...l })),
    retail_lines: retailLines.map((l) => ({ ...l })),
    // The legacy alias travels too, so a payload written against either name renders.
    dealer_lines: retailLines.map((l) => ({ ...l })),
    unclassified_lines: unclassifiedLines.map((l) => ({ ...l })),
  };
}

function buildLocations(productCode: string): OrderSummaryLocations {
  const row = ROWS.find((r) => r.product_code === productCode);
  const legacy = frontPlanningScenario() === 'legacy';
  const grain = runGrainFields().decision_grain;
  const decided = sessionDecisions.get(productCode);
  const locations = scenarioLocations(productCode);
  const allocations = decided?.location_allocations ?? row?.location_allocations ?? null;
  return {
    product_code: productCode,
    decision_grain: grain,
    is_legacy: legacy,
    uom: row?.uom ?? null,
    uom_decimal_places: legacy ? null : (row?.uom_decimal_places ?? 0),
    suggested_qty: row?.suggested_qty ?? 0,
    chosen_qty: decided?.chosen_qty ?? row?.chosen_qty ?? null,
    locations: locations.map((l) => ({
      ...l,
      allocated_qty:
        allocations?.find((a) => a.warehouse_code === l.warehouse_code)?.allocated_qty ??
        (legacy ? null : l.allocated_qty),
    })),
  };
}

// ── the mocked calls ────────────────────────────────────────────────────────

/** The mocked report GET. */
export async function mockOrderSummary(): Promise<OrderSummaryReport> {
  const scenario = frontPlanningScenario();
  const grain = runGrainFields();
  return {
    run_id: MOCK_RUN_ID,
    as_of: AS_OF,
    generated_at: GENERATED_AT,
    decision_grain: grain.decision_grain,
    is_legacy: scenario === 'legacy',
    rows: scenarioRows(),
  };
}

/** The mocked aggregate drill. */
export async function mockOrderSummaryDemand(
  productCode: string,
  kind: OrderSummaryDemandKind,
): Promise<OrderSummaryDemandDrill> {
  return buildDrill(productCode, kind);
}

/** The mocked member-location drill (AC-F08). */
export async function mockOrderSummaryLocations(
  productCode: string,
): Promise<OrderSummaryLocations> {
  return buildLocations(productCode);
}

/** The mocked supplier candidates. */
export async function mockOrderSummarySuppliers(
  productCode: string,
): Promise<OrderSummarySuppliers> {
  return SUMMARY_ORDER_FIXTURES.suppliers(productCode);
}

/**
 * The mocked decision POST. Remembers the choice for the rest of the session.
 *
 * It refuses in the two ways the route refuses (see the contract at the top of
 * `services/summaryOrderService.ts`), because a prototype that always says yes
 * cannot show what a refusal looks like:
 *
 * - too many fractional digits for the row's frozen precision (the 422);
 * - a run whose stamped grain is not `product`, or a legacy run (the 409).
 */
export async function mockRecordOrderDecision(
  productCode: string,
  input: OrderSummaryDecisionInput,
): Promise<OrderSummaryDecisionResult> {
  const scenario = frontPlanningScenario();
  const row = ROWS.find((r) => r.product_code === productCode);

  if (scenario === 'legacy') {
    throw new Error(
      'This plan was created before front planning and is read only. Create a new plan to decide quantities.',
    );
  }
  if (scenario === 'location' || scenario === 'decision_error') {
    throw new Error(
      'This plan is decided at Location grain. Open the per-location plan to decide this product.',
    );
  }

  const dp = decimalPlacesOf(row?.uom_decimal_places);
  if (exceedsPrecision(String(input.chosen_qty), dp)) {
    throw new Error(precisionError(dp, row?.uom ?? null));
  }

  const supplier = (SUPPLIERS[productCode] ?? []).find(
    (c) => c.supplier_code === input.supplier_code,
  );
  const result: OrderSummaryDecisionResult = {
    product_code: productCode,
    chosen_qty: input.chosen_qty,
    suggested_qty: row?.suggested_qty ?? 0,
    chosen_supplier_code: input.supplier_code,
    chosen_supplier_name: supplier?.supplier_name ?? input.supplier_code,
    decided_by: 'Loo Keng Hoe',
    decided_at: '2026-08-03T10:14:00',
    location_allocations: splitAcrossLocations(
      input.chosen_qty,
      LOCATIONS[productCode] ?? [],
      dp,
    ),
  };
  sessionDecisions.set(productCode, result);
  return result;
}
