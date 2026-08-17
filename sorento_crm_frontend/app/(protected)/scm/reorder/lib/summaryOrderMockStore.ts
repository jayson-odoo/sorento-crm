/**
 * ============================================================================
 * SCM Purchasing and Fulfilment - SUMMARY ORDER REPORT MOCK STORE (Phase 1 only)
 * ============================================================================
 * Deterministic fixtures for the Summary Order Report (UAC Groups C2 + C3), so
 * the prototype can be walked with NO backend. Phase 2 flips
 * `USE_SUMMARY_ORDER_MOCKS` to false in `services/summaryOrderService.ts` and
 * DELETES this file. Nothing else imports it except its own tests.
 *
 * Every figure is shaped after the real database, not invented: product codes
 * (`B2155-NL-BLUE`, `SRTWT7408`, `SRTBS4832`), the `BRW` fulfilment pool and its
 * `BRW-IB` / `BRW-BB` bins, and the Chinese sanitary-ware suppliers whose costs
 * are quoted ex-works in CNY.
 *
 * The rows are chosen to make every state in the ACs reachable by clicking:
 *
 *   - `B2155-NL-BLUE`  chosen 600 against a shortfall of 278. A chosen quantity
 *                      ABOVE the shortfall is the normal case, not a warning
 *                      (AC-C2.7). Carries BOTH a demand rate and dimensions, so
 *                      the consequence panel can state all five figures. Its
 *                      dealer drill holds the 2-unit line that has waited 214
 *                      days, which outranks the 96-unit line raised in May
 *                      (AC-C2.4), and a supplier that has NEVER delivered it
 *                      while quoting the lowest cost (AC-C2.5).
 *   - `SRTWT7408`      the first row of the first report anyone read: 4,397 in
 *                      the pool against 307 of demand, so nothing to buy. Has a
 *                      demand rate but NO recorded dimensions, so the volume
 *                      figure must name the missing input.
 *   - `SRTBS4832`      the ADR-0011 case: net position +133 yet 67 short on a
 *                      date, because the PO of 200 lands 22 days late. Has
 *                      NEITHER a demand rate nor dimensions.
 *   - `SRTSK2210`      last bought in 2021. Its only supplier is flagged stale,
 *                      which is what separates a fast mover from a dead line
 *                      (AC-C2.6), and its single dealer line has waited 402 days.
 *   - `SRTSH6120`      already decided, at exactly the engine's suggestion.
 *   - `SRTAC0904`      nothing to decide and no supplier on file, so the empty
 *                      states are reachable.
 *
 * Deterministic by construction: no `Math.random`, no `Date.now`. Every
 * `days_outstanding` and `stale_days` is the whole-day count from its own date
 * to `AS_OF`, so a reader can check any of them by hand.
 * ============================================================================
 */
import type {
  OrderSummaryDecisionInput,
  OrderSummaryDecisionResult,
  OrderSummaryDemandDrill,
  OrderSummaryDemandKind,
  OrderSummaryReport,
  OrderSummaryRow,
  OrderSummarySuppliers,
} from '../types/summaryOrder.types';

/** Phase-1 flag. Phase 2 sets this false and deletes the file. */
export const USE_SUMMARY_ORDER_MOCKS = false;

/** How long the mock takes to "fetch", so the loading skeleton is actually visible. */
const MOCK_LATENCY_MS = 400;

/** The date every ageing figure below is counted to. */
export const AS_OF = '2026-08-03';

/** Opaque run key. Identifies the week; never rendered. */
export const MOCK_RUN_ID = 'run-2026-w32';

const GENERATED_AT = '2026-08-03T07:05:00';

/**
 * The Order summary tile's count: short products with no quantity decided yet.
 * A constant here rather than a query in `ReorderPlanningView`, so opening the
 * plan does not fetch a whole report just to put a number on a card. Phase 2
 * feeds it from the run summary, alongside `MOCK_PLAN_TILE_COUNTS`.
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
    dealer_outstanding: 186,
    qty_on_order: 120,
    qty_in_transit: 200,
    shortfall: 278,
    suggested_qty: 300,
    chosen_qty: 600,
    chosen_supplier_code: 'GDS',
    chosen_supplier_name: 'Guangdong Sanitary Ware',
    decided_by: 'Loo Keng Hoe',
    decided_at: '2026-08-03T09:41:00',
    avg_daily_demand: 3.6,
    unit_volume_cbm: 0.082,
    spare_lands_at: 'BRW',
    project_demand_line_count: 3,
    dealer_outstanding_line_count: 4,
    max_days_outstanding: 214,
  },
  {
    product_code: 'SRTWT7408',
    product_name: 'Wall-hung WC 7408',
    uom: 'PCS',
    on_hand: 4397,
    project_demand: 307,
    dealer_outstanding: 0,
    qty_on_order: 0,
    qty_in_transit: 0,
    shortfall: 0,
    suggested_qty: 0,
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
    dealer_outstanding_line_count: 0,
    max_days_outstanding: null,
  },
  {
    product_code: 'SRTBS4832',
    product_name: 'Basin mixer 4832',
    uom: 'PCS',
    on_hand: 140,
    project_demand: 207,
    dealer_outstanding: 0,
    qty_on_order: 200,
    qty_in_transit: 0,
    // Net position is +133 and the item is still 67 short, because the PO of 200
    // lands 25 Aug against an order due 3 Aug. The dated engine, not on-hand maths.
    shortfall: 67,
    suggested_qty: 100,
    chosen_qty: null,
    chosen_supplier_code: null,
    chosen_supplier_name: null,
    decided_by: null,
    decided_at: null,
    avg_daily_demand: null,
    unit_volume_cbm: null,
    spare_lands_at: 'BRW',
    project_demand_line_count: 2,
    dealer_outstanding_line_count: 0,
    max_days_outstanding: null,
  },
  {
    product_code: 'SRTSK2210',
    product_name: 'Kitchen sink 2210',
    uom: 'PCS',
    on_hand: 12,
    project_demand: 0,
    dealer_outstanding: 8,
    qty_on_order: 0,
    qty_in_transit: 0,
    shortfall: 8,
    // Rounded up to the supplier's minimum order of 50.
    suggested_qty: 50,
    chosen_qty: null,
    chosen_supplier_code: null,
    chosen_supplier_name: null,
    decided_by: null,
    decided_at: null,
    avg_daily_demand: 0.04,
    unit_volume_cbm: 0.145,
    spare_lands_at: 'BRW-IB',
    project_demand_line_count: 0,
    dealer_outstanding_line_count: 1,
    max_days_outstanding: 402,
  },
  {
    product_code: 'SRTSH6120',
    product_name: 'Shower set 6120',
    uom: 'SET',
    on_hand: 0,
    project_demand: 140,
    dealer_outstanding: 35,
    qty_on_order: 90,
    qty_in_transit: 60,
    shortfall: 25,
    suggested_qty: 40,
    chosen_qty: 40,
    chosen_supplier_code: 'FSC',
    chosen_supplier_name: 'Foshan Ceramics',
    decided_by: 'Loo Keng Hoe',
    decided_at: '2026-08-03T09:52:00',
    avg_daily_demand: 1.8,
    unit_volume_cbm: 0.21,
    spare_lands_at: 'BRW',
    project_demand_line_count: 2,
    dealer_outstanding_line_count: 2,
    max_days_outstanding: 47,
  },
  {
    product_code: 'SRTAC0904',
    product_name: 'Accessory pack 0904',
    uom: 'PCS',
    on_hand: 1240,
    project_demand: 0,
    dealer_outstanding: 0,
    qty_on_order: 0,
    qty_in_transit: 0,
    shortfall: 0,
    suggested_qty: 0,
    chosen_qty: null,
    chosen_supplier_code: null,
    chosen_supplier_name: null,
    decided_by: null,
    decided_at: null,
    avg_daily_demand: null,
    unit_volume_cbm: 0.006,
    spare_lands_at: 'BRW',
    project_demand_line_count: 0,
    dealer_outstanding_line_count: 0,
    max_days_outstanding: null,
  },
];

// ── demand drills ───────────────────────────────────────────────────────────

/** Project lines, ordered by required date. Sums match the row aggregate. */
const PROJECT_LINES: Record<string, OrderSummaryDemandDrill['project_lines']> = {
  'B2155-NL-BLUE': [
    {
      project_name: 'Maryam Tuju Residence',
      so_number: 'SO-2026-0311',
      qty: 260,
      required_date: '2026-09-15',
    },
    {
      project_name: 'Setia Mutiara City',
      so_number: 'SO-2026-0342',
      qty: 140,
      required_date: '2026-10-02',
    },
    {
      project_name: 'Bandar Baru Development',
      so_number: 'SO-2026-0357',
      qty: 80,
      required_date: '2026-11-20',
    },
  ],
  SRTWT7408: [
    {
      project_name: 'Bandar Baru Development',
      so_number: 'SO-2026-0357',
      qty: 67,
      required_date: '2026-08-14',
    },
    {
      project_name: 'Setia Mutiara City',
      so_number: 'SO-2026-0361',
      qty: 240,
      required_date: '2026-09-30',
    },
  ],
  SRTBS4832: [
    {
      project_name: 'Maryam Tuju Residence',
      so_number: 'SO-2026-0311',
      qty: 135,
      required_date: '2026-07-01',
    },
    {
      project_name: 'Maryam Tuju Residence',
      so_number: 'SO-2026-0342',
      qty: 72,
      required_date: '2026-08-03',
    },
  ],
  SRTSH6120: [
    {
      project_name: 'Ipoh Riverside',
      so_number: 'SO-2026-0349',
      qty: 60,
      required_date: '2026-08-19',
    },
    {
      project_name: 'Ipoh Riverside',
      so_number: 'SO-2026-0372',
      qty: 80,
      required_date: '2026-10-15',
    },
  ],
};

/**
 * Dealer lines, WORST-FIRST by days outstanding (AC-C2.4). The order is the
 * server's, not the client's: the 2-unit line that has waited 214 days sits
 * above the 96-unit line raised in May, which is the whole point of the column.
 */
const DEALER_LINES: Record<string, OrderSummaryDemandDrill['dealer_lines']> = {
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
  // No supplier on file at all, so the candidate empty state is reachable.
  SRTAC0904: [],
};

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
  };
}

// ── named fixtures ──────────────────────────────────────────────────────────

/** Named fixtures, exported so the component tests assert the SAME figures. */
export const SUMMARY_ORDER_FIXTURES = {
  report: (): OrderSummaryReport => ({
    run_id: MOCK_RUN_ID,
    as_of: AS_OF,
    generated_at: GENERATED_AT,
    rows: ROWS.map((r) => ({ ...r })),
  }),
  /** A run with nothing to decide, for the empty state. */
  emptyReport: (): OrderSummaryReport => ({
    run_id: MOCK_RUN_ID,
    as_of: AS_OF,
    generated_at: GENERATED_AT,
    rows: [],
  }),
  row: (productCode: string): OrderSummaryRow => {
    const found = ROWS.find((r) => r.product_code === productCode);
    if (!found) throw new Error(`No mock row for ${productCode}`);
    return { ...found };
  },
  demand: (productCode: string, kind: OrderSummaryDemandKind): OrderSummaryDemandDrill =>
    buildDrill(productCode, kind),
  suppliers: (productCode: string): OrderSummarySuppliers => ({
    product_code: productCode,
    stale_after_days: STALE_AFTER_DAYS,
    candidates: (SUPPLIERS[productCode] ?? []).map((c) => ({ ...c })),
  }),
};

function buildDrill(
  productCode: string,
  kind: OrderSummaryDemandKind,
): OrderSummaryDemandDrill {
  const projectLines = kind === 'project' ? (PROJECT_LINES[productCode] ?? []) : [];
  const dealerLines = kind === 'dealer' ? (DEALER_LINES[productCode] ?? []) : [];
  const total =
    kind === 'project'
      ? projectLines.reduce((sum, l) => sum + l.qty, 0)
      : dealerLines.reduce((sum, l) => sum + l.qty, 0);
  return {
    product_code: productCode,
    kind,
    total_qty: total,
    project_lines: projectLines.map((l) => ({ ...l })),
    dealer_lines: dealerLines.map((l) => ({ ...l })),
  };
}

// ── the mocked calls ────────────────────────────────────────────────────────

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

/** The mocked report GET. Resolves after a delay so the skeleton is real. */
export async function mockOrderSummary(): Promise<OrderSummaryReport> {
  await sleep(MOCK_LATENCY_MS);
  return {
    run_id: MOCK_RUN_ID,
    as_of: AS_OF,
    generated_at: GENERATED_AT,
    rows: ROWS.map((r) => applyDecisions({ ...r })),
  };
}

/** The mocked aggregate drill. */
export async function mockOrderSummaryDemand(
  productCode: string,
  kind: OrderSummaryDemandKind,
): Promise<OrderSummaryDemandDrill> {
  await sleep(MOCK_LATENCY_MS);
  return buildDrill(productCode, kind);
}

/** The mocked supplier candidates. */
export async function mockOrderSummarySuppliers(
  productCode: string,
): Promise<OrderSummarySuppliers> {
  await sleep(MOCK_LATENCY_MS);
  return SUMMARY_ORDER_FIXTURES.suppliers(productCode);
}

/** The mocked decision POST. Remembers the choice for the rest of the session. */
export async function mockRecordOrderDecision(
  productCode: string,
  input: OrderSummaryDecisionInput,
): Promise<OrderSummaryDecisionResult> {
  await sleep(MOCK_LATENCY_MS);
  const row = ROWS.find((r) => r.product_code === productCode);
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
  };
  sessionDecisions.set(productCode, result);
  return result;
}
