/**
 * Phase 1 fixtures for Fulfilment Planning, served only when `NEXT_PUBLIC_FULFILMENT_MOCK=1`.
 *
 * THROWAWAY BY DESIGN. These die when Phase 2 wires the real endpoints
 * (PLAN-fulfilment-planning-from-autocount-so section 9). Component tests carry their own
 * fixtures; a second copy of these shapes would drift from the real one.
 *
 * Everything here is REAL-SHAPED: the sales-order numbers, customers, project strings, item
 * codes, open quantities, required dates and warehouse codes were read out of the live scratch
 * database `sorento_scm_e2e_stack` on 18 August 2026, so the screen is recognisable rather than
 * plausible. Two liberties are taken and are the only ones:
 *
 *   1. Each order carries the FIRST FEW of its real lines, not all of them. `line_count` and
 *      `outstanding_qty` on the row are the real whole-order totals, so a 40-line order says 40
 *      and shows 5. Loading 16,879 lines into a fixture file buys nothing.
 *   2. The proposed Reserve / incoming / Buy split is COMPUTED here (`proposeComponents`), not
 *      measured. There is no engine in Phase 1; the split exists so the shape of a proposal is
 *      legible and so it always balances. Its reasons name the line's real location.
 *
 * The one fact the fixtures make sure to show honestly is the captain's decision: the fulfilment
 * location is the CORE sales-order line's own, per line, and SO366992 (which came from the Order
 * Inquiry sheet) has none on any line and therefore cannot be planned until its sales order says
 * where to fulfil from.
 */
import type {
  AdoptSalesOrderResult,
  FulfilmentPlanningListEnvelope,
  FulfilmentPlanningListParams,
  FulfilmentPlanningRow,
  ReconciliationSummary,
  SupplyComponent,
  SupplyLine,
  SupplyProposal,
  SupplySpoRef,
} from '../../types/fulfilmentPlanning.types';
import {
  planningRowReference,
  sortByEarliestRequired,
} from '../../lib/fulfilmentPlanningRows';

interface FixtureLine {
  item_code: string;
  open_qty: string;
  required_date: string;
  /** Warehouse code off the core line. Empty string is the Order Inquiry sheet's silence. */
  warehouse: string;
}

interface FixtureOrder {
  so_number: string;
  sales_order_id: string;
  customer_name: string;
  /** From the core order's `internal_note` project string. Null when the sheet named none. */
  project_label: string | null;
  earliest_required_date: string;
  /** The real whole-order totals, even though `lines` carries a subset. */
  line_count: number;
  outstanding_qty: string;
  /**
   * Present when this order has ALREADY been planned in the fixture world. Absent means the row
   * reads Not started and Start planning is its one action.
   */
  planning_record_id?: string;
  planned_state?: 'needs_cs_review' | 'confirmed';
  lines: FixtureLine[];
}

/**
 * The AutoCount sales-order book, as CS sees it. Every one of these is a real outstanding
 * project-class order in the scratch DB.
 */
const ORDERS: FixtureOrder[] = [
  {
    so_number: 'SO391698',
    sales_order_id: 'so-391698',
    customer_name: 'OIB CONSTRUCTION SDN BHD (PROJECT)',
    project_label: 'OIB CONSTRUCTION / MYRA DAHLIA 9307, SALAK TINGGI / SEPANG',
    earliest_required_date: '2022-07-03',
    line_count: 40,
    outstanding_qty: '5488',
    lines: [
      { item_code: 'WESERP10B', open_qty: '12', required_date: '2022-07-03', warehouse: 'BRW-IB' },
      { item_code: 'SRTWC7405-SC', open_qty: '216', required_date: '2026-03-02', warehouse: 'BRW-IB' },
      { item_code: 'SRTWCX7405-RL-S-PJ', open_qty: '216', required_date: '2026-03-02', warehouse: 'BRW-IB' },
      { item_code: 'SRTWCY7405-PJ', open_qty: '216', required_date: '2026-03-02', warehouse: 'BRW-IB' },
      { item_code: 'WESERP10B', open_qty: '216', required_date: '2026-03-02', warehouse: 'BRW-IB' },
    ],
  },
  {
    so_number: 'SO324265',
    sales_order_id: 'so-324265',
    customer_name: 'MASUKA BINA SDN BHD (PROJECT)',
    project_label: 'MASUKA/THE SENZE PICC/TOWER NORMAL UNIT/UPGRADED UNIT',
    earliest_required_date: '2024-12-03',
    line_count: 32,
    outstanding_qty: '1120',
    lines: [
      { item_code: 'SRT8304', open_qty: '23', required_date: '2024-12-03', warehouse: 'BRW-BB' },
      { item_code: 'SRTKS2405', open_qty: '4', required_date: '2026-05-04', warehouse: 'BRW-BB' },
      { item_code: 'TPE-9201', open_qty: '130', required_date: '2026-05-04', warehouse: 'BRW-BB' },
      { item_code: 'TPE-9201', open_qty: '25', required_date: '2026-05-04', warehouse: 'BRW-BB' },
      { item_code: 'BT012-CR', open_qty: '45', required_date: '2026-06-01', warehouse: 'BRW-BB' },
    ],
  },
  {
    so_number: 'SO346436',
    sales_order_id: 'so-346436',
    customer_name: 'GLOBAL INGRESS SDN BHD (PROJECT)',
    project_label: 'GLOBAL INGRESS/ 252U RMMJ TAMAN IMPIAN EMAS',
    earliest_required_date: '2025-04-23',
    line_count: 4,
    outstanding_qty: '550',
    // Two locations on one order, which is exactly why the location is a per-line fact and not
    // one answer for the whole order.
    lines: [
      { item_code: 'TPE-9201', open_qty: '150', required_date: '2025-04-23', warehouse: 'BRW' },
      { item_code: 'TPE-9201', open_qty: '100', required_date: '2025-04-23', warehouse: 'BRW' },
      { item_code: 'CKS1050', open_qty: '150', required_date: '2026-01-10', warehouse: 'BRW-IB' },
      { item_code: 'CKSW015', open_qty: '150', required_date: '2026-01-10', warehouse: 'BRW-IB' },
    ],
  },
  {
    so_number: 'SO366992',
    sales_order_id: 'so-366992',
    customer_name: 'BUIMACO SDN BHD',
    project_label: 'BUIMACO / UNITIN ENG/ TMN PUCHONG LEGENDA',
    earliest_required_date: '2025-05-02',
    line_count: 22,
    outstanding_qty: '520',
    // Came from the Order Inquiry sheet, which states no location on any line. Nothing here is
    // defaulted: the lines say so and point at the sales order.
    lines: [
      { item_code: 'SRTFH15-HD', open_qty: '24', required_date: '2025-05-02', warehouse: '' },
      { item_code: 'SRTSA830-PJ', open_qty: '24', required_date: '2025-05-02', warehouse: '' },
      { item_code: 'SRTSC03-ABS-NL', open_qty: '24', required_date: '2025-05-02', warehouse: '' },
      { item_code: 'SRTSH22512', open_qty: '24', required_date: '2025-05-02', warehouse: '' },
      { item_code: 'SRTSH22512-N', open_qty: '24', required_date: '2025-05-02', warehouse: '' },
    ],
  },
  {
    so_number: 'SO345418',
    sales_order_id: 'so-345418',
    customer_name: 'PEMBINAAN YUEN SENG SDN BHD (PROJECT)',
    // The core order carries no project string, so the column states its absence.
    project_label: null,
    earliest_required_date: '2025-06-15',
    line_count: 1,
    outstanding_qty: '202',
    lines: [
      { item_code: 'WESERP10B', open_qty: '202', required_date: '2025-06-15', warehouse: 'BRW-BB' },
    ],
  },
  {
    so_number: 'SO369758',
    sales_order_id: 'so-369758',
    customer_name: 'JUBIN BMS (1990) SDN BHD (PROJECT)',
    project_label: 'JUBIN BMS (1990)/VISTA LAVENDAR',
    earliest_required_date: '2025-07-31',
    line_count: 108,
    outstanding_qty: '6835',
    lines: [
      { item_code: 'CB6622', open_qty: '44', required_date: '2025-07-31', warehouse: 'BRW-BB' },
      { item_code: 'CB6622', open_qty: '44', required_date: '2025-07-31', warehouse: 'BRW-BB' },
      { item_code: 'CB6622', open_qty: '77', required_date: '2025-07-31', warehouse: 'BRW-BB' },
      { item_code: 'CB6622', open_qty: '44', required_date: '2025-07-31', warehouse: 'BRW-BB' },
      { item_code: 'B2154-NL', open_qty: '80', required_date: '2026-05-01', warehouse: 'BRW-BB' },
    ],
  },
  {
    so_number: 'SO396071',
    sales_order_id: 'so-396071',
    customer_name: 'ASASJAYA HARDWARE ENTERPRISE (PROJECT)',
    project_label: 'ASASJAYA/THE STRAITS VIEW GARDEN/JB',
    earliest_required_date: '2025-09-01',
    line_count: 17,
    outstanding_qty: '6588',
    lines: [
      { item_code: 'SRTSA831-PJ', open_qty: '183', required_date: '2025-09-01', warehouse: 'BRW-BB' },
      { item_code: 'BT012-CR', open_qty: '183', required_date: '2026-09-01', warehouse: 'BRW-BB' },
      { item_code: 'BT012-CR', open_qty: '549', required_date: '2026-09-01', warehouse: 'BRW-BB' },
      { item_code: 'CB600', open_qty: '549', required_date: '2026-09-01', warehouse: 'BRW-BB' },
      { item_code: 'CB900', open_qty: '183', required_date: '2026-09-01', warehouse: 'BRW-BB' },
    ],
  },
  {
    so_number: 'SO368874',
    sales_order_id: 'so-368874',
    customer_name: 'EMB EMPRESS (MALAYSIA) SDN BHD (PROJECT)',
    project_label: 'EMB EMPRESS / PINNACLE ARA DAMANSARA - TOWER A / VESTLAND',
    earliest_required_date: '2025-09-22',
    line_count: 14,
    outstanding_qty: '6306',
    planning_record_id: 'pso-adopted-368874',
    planned_state: 'needs_cs_review',
    lines: [
      { item_code: 'SRTPW0035-CR', open_qty: '364', required_date: '2025-09-22', warehouse: 'BRW-IB' },
      { item_code: 'B2155-NL-BLUE', open_qty: '1079', required_date: '2026-05-01', warehouse: 'BRW-IB' },
      { item_code: 'C-FH14', open_qty: '728', required_date: '2026-05-01', warehouse: 'BRW-IB' },
      { item_code: 'CB8905-DIY', open_qty: '495', required_date: '2026-05-01', warehouse: 'BRW-IB' },
      { item_code: 'CBT001-B', open_qty: '364', required_date: '2026-05-01', warehouse: 'BRW-IB' },
    ],
  },
  {
    so_number: 'SO364368',
    sales_order_id: 'so-364368',
    customer_name: 'JAYAPLUS DEVELOPMENT SDN BHD (PROJECT)',
    project_label: 'JAYAPLUS/PARAGON/BLOCK D/JB',
    earliest_required_date: '2025-12-16',
    line_count: 100,
    outstanding_qty: '10470',
    planning_record_id: 'pso-adopted-364368',
    planned_state: 'confirmed',
    lines: [
      { item_code: 'SRTWT907SS', open_qty: '70', required_date: '2025-12-16', warehouse: 'BRW-BB' },
      { item_code: 'CB309', open_qty: '118', required_date: '2026-11-01', warehouse: 'BRW-BB' },
      { item_code: 'SRTWB247', open_qty: '42', required_date: '2026-11-01', warehouse: 'BRW-BB' },
      { item_code: 'SRTWB890', open_qty: '76', required_date: '2026-11-01', warehouse: 'BRW-BB' },
      { item_code: 'SRTWC8355-RL', open_qty: '117', required_date: '2026-11-01', warehouse: 'BRW-BB' },
    ],
  },
];

/**
 * Arm 2: a Project SO this system authored that has no core sales order yet. It is here so the
 * union is visible and so the Stage 1B journey keeps working beside the new one.
 */
const AUTHORED_ROWS: FulfilmentPlanningRow[] = [
  {
    row_kind: 'planning_record',
    id: 'pso-authored-000123',
    origin: 'authored',
    provisional_ref: 'PSO-000123',
    autocount_doc_no: null,
    project_id: 'project-tuju',
    project_code: 'PRJ-0042',
    project_name: 'Tuju Residences',
    project_label: 'Tuju Residences',
    customer_name: 'BUIMACO SDN BHD (PROJECT)',
    po_number: 'HQ/26/01/121',
    area_group: 'TOWER',
    status: 'published',
    line_count: 99,
    lines_linked: 0,
    exception_count: 3,
    outstanding_qty: '2418',
    earliest_required_date: '2026-07-01',
    review_state: 'awaiting_reconciliation',
    updated_at: '2026-08-14T02:15:00',
  },
];

/**
 * Orders adopted during this browser session, so pressing Start planning actually moves the row
 * out of Not started the way the real one will. Module-level and deliberately not persisted: a
 * reload is the fixtures' reset button.
 */
const adoptedThisSession = new Map<string, string>();

function planningRecordId(order: FixtureOrder): string | undefined {
  return order.planning_record_id ?? adoptedThisSession.get(order.sales_order_id);
}

function rowFor(order: FixtureOrder): FulfilmentPlanningRow {
  const recordId = planningRecordId(order);
  const state = recordId ? (order.planned_state ?? 'needs_cs_review') : 'not_started';
  return {
    row_kind: 'sales_order',
    id: recordId ?? null,
    sales_order_id: order.sales_order_id,
    so_number: order.so_number,
    origin: recordId ? 'adopted' : null,
    // An adopted record's own reference IS the sales-order number: the AutoCount book named it,
    // nobody here authored a second reference for it.
    provisional_ref: recordId ? order.so_number : null,
    autocount_doc_no: recordId ? order.so_number : null,
    project_id: null,
    project_code: null,
    project_name: null,
    project_label: order.project_label,
    customer_name: order.customer_name,
    po_number: null,
    area_group: null,
    status: recordId ? 'adopted' : null,
    line_count: order.line_count,
    lines_linked: recordId ? order.line_count : 0,
    exception_count: 0,
    outstanding_qty: order.outstanding_qty,
    earliest_required_date: order.earliest_required_date,
    review_state: state,
    updated_at: recordId ? '2026-08-17T09:40:00' : null,
  };
}

function orderByRecordId(psoId: string): FixtureOrder | undefined {
  return ORDERS.find((order) => planningRecordId(order) === psoId);
}

function matchesQuery(row: FulfilmentPlanningRow, query: string): boolean {
  if (!query) return true;
  const needle = query.trim().toLowerCase();
  return [
    row.so_number,
    row.provisional_ref,
    row.autocount_doc_no,
    row.customer_name,
    row.project_label,
    row.project_code,
    row.area_group,
  ]
    .filter(Boolean)
    .some((value) => String(value).toLowerCase().includes(needle));
}

export function mockWorklist(
  params: FulfilmentPlanningListParams = {},
): FulfilmentPlanningListEnvelope {
  const limit = params.limit ?? 25;
  const page = params.page ?? 1;
  const all = sortByEarliestRequired([...ORDERS.map(rowFor), ...AUTHORED_ROWS]);
  const filtered = all
    .filter((row) => !params.review_state || row.review_state === params.review_state)
    .filter((row) => matchesQuery(row, params.query ?? ''));
  const start = (page - 1) * limit;
  return {
    data: filtered.slice(start, start + limit),
    total: filtered.length,
    page,
    limit,
  };
}

/**
 * Start planning. Idempotent by construction: a second press finds the record already in the
 * session map and answers with it, which is what the real endpoint promises (AC-FP08).
 */
export function mockAdopt(salesOrderId: string): AdoptSalesOrderResult {
  const order = ORDERS.find((entry) => entry.sales_order_id === salesOrderId);
  if (!order) throw new Error('That sales order is not in the fulfilment planning list');
  const existing = planningRecordId(order);
  if (existing) {
    return {
      project_sales_order_id: existing,
      so_number: order.so_number,
      review_state: order.planned_state ?? 'needs_cs_review',
      already_adopted: true,
    };
  }
  const recordId = `pso-adopted-${order.so_number.replace(/^SO/, '')}`;
  adoptedThisSession.set(order.sales_order_id, recordId);
  return {
    project_sales_order_id: recordId,
    so_number: order.so_number,
    review_state: 'needs_cs_review',
    already_adopted: false,
  };
}

/**
 * Reconciliation on an ADOPTED order. There is no second document to disagree with, so the card
 * states that in one sentence and offers Re-sync; it is never hidden and never blank.
 */
export function mockReconciliation(psoId: string): ReconciliationSummary {
  const order = orderByRecordId(psoId);
  if (!order) throw new Error('That sales order could not be found');
  return {
    project_sales_order_id: psoId,
    provisional_ref: order.so_number,
    autocount_doc_no: order.so_number,
    project_id: null,
    project_code: null,
    project_name: null,
    customer_name: order.customer_name,
    po_number: null,
    area_group: null,
    status: 'adopted',
    review_state: order.planned_state ?? 'needs_cs_review',
    header: {
      outcome: 'adopted',
      core_so_number: order.so_number,
      reason:
        'This order came from the AutoCount sales-order book, so there is no separately authored Project SO to compare it against.',
    },
    lines: order.lines.map((line, index) => ({
      id: `${psoId}-line-${index + 1}`,
      line_no: index + 1,
      product_code: line.item_code,
      description: line.item_code,
      qty: line.open_qty,
      uom: null,
      delivery_date: line.required_date,
      stock_location: line.warehouse || null,
      link: 'linked' as const,
      candidate_count: 1,
      reason: 'Mirrored from the core sales order line.',
    })),
    exceptions: [],
    lines_total: order.lines.length,
    lines_linked: order.lines.length,
  };
}

/** Deterministic, so the same line proposes the same split on every render. */
function seedOf(itemCode: string, index: number): number {
  let seed = index + 1;
  for (const character of itemCode) seed = (seed * 31 + character.charCodeAt(0)) % 997;
  return seed;
}

const SCALE = 10_000;
const toMinorQty = (qty: string) => Math.round(Number.parseFloat(qty) * SCALE);
const fromMinorQty = (minor: number) => String(Number((minor / SCALE).toFixed(4)));

/**
 * The Reserve / incoming / Buy split, computed so it always balances against the open quantity.
 * The engine is Phase 2's job; this exists so the SHAPE of a proposal is legible today, and the
 * reasons name the line's own location because that is the decision on show.
 */
function proposeComponents(
  line: FixtureLine,
  seed: number,
): { components: SupplyComponent[]; timely: SupplySpoRef[]; advisory: SupplySpoRef[] } {
  const openMinor = toMinorQty(line.open_qty);
  const hasFreeStock = seed % 3 !== 0;
  const hasIncoming = seed % 2 === 0;

  const reserveMinor = hasFreeStock ? Math.round(openMinor * 0.35) : 0;
  const timelyMinor = hasIncoming ? Math.round(openMinor * 0.2) : 0;
  const buyMinor = Math.max(openMinor - reserveMinor - timelyMinor, 0);

  const components: SupplyComponent[] = [];
  const timely: SupplySpoRef[] = [];
  const advisory: SupplySpoRef[] = [];

  if (timelyMinor > 0) {
    const spo = `2026${String((seed % 12) + 1).padStart(2, '0')}-S${String(seed % 9999).padStart(4, '0')}`;
    timely.push({ spo_number: spo, arrival_date: line.required_date, qty: fromMinorQty(timelyMinor) });
    components.push({
      kind: 'timely_spo',
      qty: fromMinorQty(timelyMinor),
      reason: `${spo} arrives at ${line.warehouse} on or before the required date.`,
      source_location: line.warehouse,
    });
  }
  if (reserveMinor > 0) {
    components.push({
      kind: 'reserve',
      qty: fromMinorQty(reserveMinor),
      reason: `Free unclaimed stock at ${line.warehouse} covers this much by the required date.`,
      source_location: line.warehouse,
      source_warehouse_id: `wh-${line.warehouse.toLowerCase()}`,
    });
  }
  if (buyMinor > 0) {
    components.push({
      kind: 'buy',
      qty: fromMinorQty(buyMinor),
      reason:
        reserveMinor + timelyMinor > 0
          ? `The residual is not covered at ${line.warehouse} by the required date, so it is bought.`
          : `Nothing free and nothing incoming at ${line.warehouse} by the required date.`,
    });
  }
  if (seed % 5 === 0) {
    advisory.push({
      spo_number: `202612-S${String((seed % 9999) + 1).padStart(4, '0')}`,
      arrival_date: '2027-01-15',
      qty: fromMinorQty(Math.round(openMinor * 0.5)),
    });
  }
  return { components, timely, advisory };
}

function supplyLine(psoId: string, line: FixtureLine, index: number): SupplyLine {
  const seed = seedOf(line.item_code, index);
  // No location on the source record means nothing is proposed at all. A Reserve of zero
  // presented as a plan would be worse than the refusal.
  if (!line.warehouse) {
    return {
      project_line_id: `${psoId}-line-${index + 1}`,
      line_no: index + 1,
      item_code: line.item_code,
      description: line.item_code,
      uom: null,
      open_qty: line.open_qty,
      required_date: line.required_date,
      fulfilment_location: null,
      fulfilment_location_missing: true,
      is_dealer_hot_selling: false,
      classification_unavailable: true,
      is_discontinued: false,
      pool_location: null,
      pool_cap: null,
      pool_reorder_level: null,
      components: [],
      timely_spo: [],
      advisory_spo: [],
      borrow_candidates: [],
    };
  }
  const { components, timely, advisory } = proposeComponents(line, seed);
  return {
    project_line_id: `${psoId}-line-${index + 1}`,
    line_no: index + 1,
    item_code: line.item_code,
    description: line.item_code,
    uom: null,
    open_qty: line.open_qty,
    required_date: line.required_date,
    fulfilment_location: line.warehouse,
    fulfilment_location_missing: false,
    is_dealer_hot_selling: seed % 4 === 0,
    classification_unavailable: false,
    is_discontinued: false,
    pool_location: 'BRW',
    pool_cap: seed % 4 === 0 ? '120' : null,
    pool_reorder_level: seed % 4 === 0 ? '80' : null,
    components,
    timely_spo: timely,
    advisory_spo: advisory,
    borrow_candidates: [],
  };
}

export function mockSupply(psoId: string): SupplyProposal {
  const order = orderByRecordId(psoId);
  if (!order) throw new Error('That sales order could not be found');
  const confirmed = order.planned_state === 'confirmed';
  const lines = order.lines.map((line, index) => supplyLine(psoId, line, index));
  return {
    project_sales_order_id: psoId,
    provisional_ref: order.so_number,
    autocount_doc_no: order.so_number,
    sales_order_number: order.so_number,
    sales_order_id: order.sales_order_id,
    project_id: null,
    project_code: null,
    project_name: null,
    status: 'adopted',
    review_state: confirmed ? 'confirmed' : 'needs_cs_review',
    decision: confirmed
      ? {
          revision_no: 1,
          state: 'active',
          confirmed_by_name: 'Nurul Aina',
          confirmed_at: '2026-08-17T09:40:00',
        }
      : null,
    lines: confirmed
      ? lines.map((line) => ({
          ...line,
          frozen: { open_qty: line.open_qty, components: line.components },
        }))
      : lines,
  };
}

/** Exported for the tests, so an assertion names a row rather than an index. */
export function mockRowFor(soNumber: string): FulfilmentPlanningRow | undefined {
  return mockWorklist({ limit: 100 }).data.find(
    (row) => planningRowReference(row) === soNumber,
  );
}
