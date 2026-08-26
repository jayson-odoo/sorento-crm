/**
 * Phase 1 fixtures for planning changes (`PLAN-so-book-diff-replanning.md`).
 *
 * `pcb-1` is the batch under review: one row per rule of the section-0 table, spread across
 * three planned orders, so every reaction and every render state (held, no hold, dealer
 * hot-selling, project hot-selling, discontinued, buy-only, buy-actioned, advance, qty up, qty
 * down, closed, new line) is on screen at once. One order is adopted (mirror of the AutoCount
 * book, SO403765) and two are authored project SOs, so the SO-number link covers both kinds.
 * `pcb-0` is a batch already applied, carrying the two safety states Apply can leave behind
 * (one order that failed, one row a later board edit superseded before Apply ran) plus the
 * `result` Apply wrote.
 *
 * Kept after the backend landed because the component tests read from it: one shape for the
 * prototype and the tests means a test cannot pass against a row the screen never saw.
 */
import type {
  BoardContribution,
  BoardTrailStep,
} from '../types/fulfilmentPlanning.types';
import type {
  PlanningChangeBatch,
  PlanningChangeBatchSummary,
  PlanningChangeBuyActionedFact,
  PlanningChangeEvidencedFact,
  PlanningChangeReserveWindowFact,
  PlanningChangeRow,
} from '../types/planningChange.types';

/** One calendar day arithmetic helper, UTC so a date-only string round-trips exactly. */
function addDays(dateStr: string, days: number): string {
  const date = new Date(`${dateStr}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

/** A fact with no supporting evidence - `dealer_hot_selling: false` needs no `where`. */
function evidencedFact(value: boolean, where: string[] = []): PlanningChangeEvidencedFact {
  return { value, where };
}

/** The 60-day reserve window, measured from the line's previous delivery date. */
function windowFact(
  fromDate: string,
  toDate: string,
  daysMoved: number,
): PlanningChangeReserveWindowFact {
  return {
    value: Math.abs(daysMoved) <= 60,
    window_days: 60,
    new_date: toDate,
    window_end: addDays(fromDate, 60),
  };
}

function buyActionedFact(value: boolean, poNumber: string | null = null): PlanningChangeBuyActionedFact {
  return { value, po_number: value ? poNumber : null };
}

/** A minimal, type-complete `BoardContribution` for a replan/qty_up proposal (AC-R07). */
function boardProposal(overrides: {
  key: string;
  sales_order_id: string;
  so_number: string;
  line_no: number;
  item_code: string;
  qty: string;
  required_date: string;
  reserveQty: string;
  reserveLocation: string;
  buyQty: string;
}): BoardContribution {
  const {
    key,
    sales_order_id,
    so_number,
    line_no,
    item_code,
    qty,
    required_date,
    reserveQty,
    reserveLocation,
    buyQty,
  } = overrides;
  const trail: BoardTrailStep[] = [
    {
      step: 1,
      kind: 'reserve_own',
      location: reserveLocation,
      warehouse_id: `wh-${reserveLocation}`,
      opening: reserveQty,
      ahead_qty: '0',
      ahead_lines: 0,
      ahead: [],
      ahead_more: 0,
      offered: reserveQty,
      taken: reserveQty,
      remaining_after: buyQty,
      outcome: 'took',
      why: `Not dealer hot-selling, so own-location stock is eligible. First in the queue here; this line takes ${reserveQty}.`,
    },
    {
      step: 2,
      kind: 'reserve_pool',
      offered: '0',
      taken: '0',
      remaining_after: buyQty,
      outcome: 'not_eligible',
      note: 'no shared pool',
      why: 'No shared pool for this product.',
    },
    {
      step: 3,
      kind: 'incoming',
      location: reserveLocation,
      warehouse_id: `wh-${reserveLocation}`,
      opening: '0',
      offered: '0',
      taken: '0',
      remaining_after: buyQty,
      outcome: 'nothing_left',
      why: 'No supplier PO arrives by the required date.',
    },
    {
      step: 4,
      kind: 'borrow',
      opening: '0',
      offered: '0',
      taken: '0',
      remaining_after: buyQty,
      outcome: 'nothing_left',
      why: 'No other location holds this product free.',
    },
    {
      step: 5,
      kind: 'buy',
      offered: buyQty,
      taken: buyQty,
      remaining_after: '0',
      outcome: 'took',
      why: 'Nothing left to take, so the remainder is bought.',
    },
  ];
  return {
    key,
    sales_order_id,
    line_id: `core-${sales_order_id}-${line_no}`,
    product_id: `prod-${item_code}`,
    so_number,
    line_no,
    item_code,
    qty,
    qty_outstanding: qty,
    required_date,
    fulfilment_location: reserveLocation,
    fulfilment_warehouse_id: `wh-${reserveLocation}`,
    unplannable: false,
    sources: [
      {
        kind: 'reserve',
        qty: reserveQty,
        location: reserveLocation,
        warehouse_id: `wh-${reserveLocation}`,
        reason: `Free unclaimed stock at ${reserveLocation} covers this much by the required date.`,
      },
      {
        kind: 'buy',
        qty: buyQty,
        location: null,
        reason: `Free stock at ${reserveLocation} ran out on this line; the residual is bought.`,
      },
    ],
    trail,
    item_flags: {
      dealer_hot_selling: false,
      dealer_hot_selling_where: [],
      project_hot_selling: false,
      project_hot_selling_where: [],
      dealer_classified: false,
      project_classified: false,
      discontinued: false,
      retail_classification_available: true,
    },
    contested: false,
    rank_score: 0,
    rank_factors: [],
    covered: false,
    decision: null,
  };
}

const ROW_1: PlanningChangeRow = {
  id: 'pcr-1',
  line_no: 3,
  item_code: 'CB231SS-NL',
  product_name: 'Concealed cistern 231SS',
  kind: 'delayed',
  from: { required_date: '2026-08-20', qty: '72', status: 'open' },
  to: { required_date: '2026-09-03', qty: '72', status: 'open' },
  days_moved: 14,
  held: {
    reserve: [{ location: 'BRW-BB', warehouse_id: 'wh-BRW-BB', qty: '66' }],
    borrow: [],
    buy_qty: '6',
    timely_spo_qty: '0',
    revision_no: 4,
  },
  facts: {
    dealer_hot_selling: evidencedFact(false),
    project_hot_selling: evidencedFact(false),
    discontinued: false,
    days_moved: 14,
    within_reserve_window: windowFact('2026-08-20', '2026-09-03', 14),
    buy_actioned: buyActionedFact(false),
  },
  suggested: 'keep',
  why: 'New date is 14 days out and inside the 60-day reserve window; the reserve stays put rather than being released and re-taken.',
  proposal: null,
  inquiry_rows: [{ id: 'oi-1', verb: 'ORDER', qty: '6', state: 'raised' }],
  decision: 'accept',
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO403765&cell=CB231SS-NL|2026-09-03',
};

const ROW_2: PlanningChangeRow = {
  id: 'pcr-2',
  line_no: 4,
  item_code: 'WESERP10B',
  product_name: 'Wall hung bidet spray',
  kind: 'delayed',
  from: { required_date: '2026-08-25', qty: '40', status: 'open' },
  to: { required_date: '2027-03-10', qty: '40', status: 'open' },
  days_moved: 197,
  held: {
    reserve: [{ location: 'MWH-IB', warehouse_id: 'wh-MWH-IB', qty: '40' }],
    borrow: [],
    buy_qty: '0',
    timely_spo_qty: '0',
    revision_no: 4,
  },
  facts: {
    dealer_hot_selling: evidencedFact(false),
    project_hot_selling: evidencedFact(false),
    discontinued: false,
    days_moved: 197,
    within_reserve_window: windowFact('2026-08-25', '2027-03-10', 197),
    buy_actioned: buyActionedFact(false),
  },
  suggested: 'release',
  why: 'New date is 197 days out, beyond the 60-day reserve window; the reserve is released back to MWH-IB rather than sitting idle for months.',
  proposal: null,
  inquiry_rows: [],
  decision: 'accept',
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO403765&cell=WESERP10B|2027-03-10',
};

const ROW_3: PlanningChangeRow = {
  id: 'pcr-3',
  line_no: 5,
  item_code: 'B2155-NL-BLUE',
  product_name: 'Basin mixer 2155 blue',
  kind: 'delayed',
  from: { required_date: '2026-09-05', qty: '30', status: 'open' },
  to: { required_date: '2026-09-26', qty: '30', status: 'open' },
  days_moved: 21,
  held: {
    reserve: [{ location: 'BRW', warehouse_id: 'wh-BRW', qty: '30' }],
    borrow: [],
    buy_qty: '0',
    timely_spo_qty: '0',
    revision_no: 4,
  },
  facts: {
    dealer_hot_selling: evidencedFact(true, ['BRW', 'BRW-IB']),
    project_hot_selling: evidencedFact(false),
    discontinued: false,
    days_moved: 21,
    within_reserve_window: windowFact('2026-09-05', '2026-09-26', 21),
    buy_actioned: buyActionedFact(false),
  },
  suggested: 'release',
  why: 'Dealer hot-selling at BRW, BRW-IB: retail needs the pool stock now, so the reserve is released back to the pool whatever the size of the delay.',
  proposal: null,
  inquiry_rows: [],
  decision: 'accept',
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO403765&cell=B2155-NL-BLUE|2026-09-26',
};

const ROW_4: PlanningChangeRow = {
  id: 'pcr-4',
  line_no: 6,
  item_code: 'CB231SS-NL',
  product_name: 'Concealed cistern 231SS',
  kind: 'delayed',
  from: { required_date: '2026-08-15', qty: '18', status: 'open' },
  to: { required_date: '2027-05-01', qty: '18', status: 'open' },
  days_moved: 259,
  held: {
    reserve: [{ location: 'MWH-IB', warehouse_id: 'wh-MWH-IB', qty: '18' }],
    borrow: [],
    buy_qty: '0',
    timely_spo_qty: '0',
    revision_no: 4,
  },
  facts: {
    dealer_hot_selling: evidencedFact(false),
    project_hot_selling: evidencedFact(false),
    discontinued: true,
    days_moved: 259,
    within_reserve_window: windowFact('2026-08-15', '2027-05-01', 259),
    buy_actioned: buyActionedFact(false),
  },
  suggested: 'keep',
  why: 'Discontinued: it cannot be bought again, so the reserve is kept whatever the size of the delay.',
  proposal: null,
  inquiry_rows: [],
  decision: 'accept',
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO403765&cell=CB231SS-NL|2027-05-01',
};

const ROW_5: PlanningChangeRow = {
  id: 'pcr-5',
  line_no: 7,
  item_code: 'WESERP10B',
  product_name: 'Wall hung bidet spray',
  kind: 'delayed',
  from: { required_date: '2026-08-22', qty: '25', status: 'open' },
  to: { required_date: '2026-09-10', qty: '25', status: 'open' },
  days_moved: 19,
  held: {
    reserve: [],
    borrow: [],
    buy_qty: '25',
    timely_spo_qty: '0',
    revision_no: 4,
  },
  facts: {
    dealer_hot_selling: evidencedFact(false),
    project_hot_selling: evidencedFact(false),
    discontinued: false,
    days_moved: 19,
    within_reserve_window: windowFact('2026-08-22', '2026-09-10', 19),
    buy_actioned: buyActionedFact(false),
  },
  suggested: 'keep',
  why: 'Only a Buy of 25 is held and purchasing has not actioned it yet; the Buy stands and the inquiry row is updated to DELAY with the previous date.',
  proposal: null,
  inquiry_rows: [{ id: 'oi-5', verb: 'ORDER', qty: '25', state: 'raised' }],
  decision: 'accept',
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO403765&cell=WESERP10B|2026-09-10',
};

const ROW_6: PlanningChangeRow = {
  id: 'pcr-6',
  line_no: 8,
  item_code: 'B2155-NL-BLUE',
  product_name: 'Basin mixer 2155 blue',
  kind: 'delayed',
  from: { required_date: '2026-08-28', qty: '18', status: 'open' },
  to: { required_date: '2026-09-18', qty: '18', status: 'open' },
  days_moved: 21,
  held: {
    reserve: [],
    borrow: [],
    buy_qty: '18',
    timely_spo_qty: '0',
    revision_no: 4,
  },
  facts: {
    dealer_hot_selling: evidencedFact(false),
    project_hot_selling: evidencedFact(false),
    discontinued: false,
    days_moved: 21,
    within_reserve_window: windowFact('2026-08-28', '2026-09-18', 21),
    buy_actioned: buyActionedFact(true, 'PO2026-0412'),
  },
  suggested: 'keep',
  why: 'The Buy of 18 is already a placed purchase order (PO2026-0412); nothing in the plan changes, and the inquiry row notes the delay.',
  proposal: null,
  inquiry_rows: [{ id: 'oi-6', verb: 'ORDER', qty: '18', state: 'actioned' }],
  decision: 'accept',
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO403765&cell=B2155-NL-BLUE|2026-09-18',
};

const ROW_7: PlanningChangeRow = {
  id: 'pcr-7',
  line_no: 2,
  item_code: 'CB231SS-NL',
  product_name: 'Concealed cistern 231SS',
  kind: 'advanced',
  from: { required_date: '2027-02-18', qty: '60', status: 'open' },
  to: { required_date: '2027-02-04', qty: '60', status: 'open' },
  days_moved: -14,
  held: {
    reserve: [{ location: 'BRW-BB', warehouse_id: 'wh-BRW-BB', qty: '20' }],
    borrow: [],
    buy_qty: '40',
    timely_spo_qty: '0',
    revision_no: 2,
  },
  facts: {
    dealer_hot_selling: evidencedFact(false),
    project_hot_selling: evidencedFact(true, ['BRW-BB']),
    discontinued: false,
    days_moved: -14,
    within_reserve_window: windowFact('2027-02-18', '2027-02-04', -14),
    buy_actioned: buyActionedFact(false),
  },
  suggested: 'replan',
  why: 'Advanced 18 Feb -> 04 Feb (-14 d); the line runs the ladder again at the new date now, and the proposal below is what it found.',
  proposal: boardProposal({
    key: 'pcb-1-so400875-l2-advance',
    sales_order_id: 'so-400875',
    so_number: 'SO400875',
    line_no: 2,
    item_code: 'CB231SS-NL',
    qty: '60',
    required_date: '2027-02-04',
    reserveQty: '40',
    reserveLocation: 'BRW-BB',
    buyQty: '20',
  }),
  inquiry_rows: [{ id: 'oi-7', verb: 'ORDER', qty: '40', state: 'raised' }],
  // NOTE: the real backend now defaults a `replan` row's decision to `null` ("Leave on the
  // board") rather than `accept` - `accept` never executed anything for it (the captain's
  // own fix, 19 August 2026). Left as `accept` here only to avoid perturbing this fixture's
  // other counts (`BatchMetaStrip`'s "N lines with a decision"), which several existing
  // Phase 1 tests assert on by exact figure; the FE control itself does not read this value
  // to decide whether `Confirm`/`Amend`/`Leave on the board` is clickable.
  decision: 'accept',
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO400875&cell=CB231SS-NL|2027-02-04',
};

const ROW_8: PlanningChangeRow = {
  id: 'pcr-8',
  line_no: 3,
  item_code: 'WESERP10B',
  product_name: 'Wall hung bidet spray',
  kind: 'qty_up',
  from: { required_date: '2027-01-10', qty: '72', status: 'open' },
  to: { required_date: '2027-01-10', qty: '90', status: 'open' },
  days_moved: 0,
  held: {
    reserve: [{ location: 'BRW-BB', warehouse_id: 'wh-BRW-BB', qty: '72' }],
    borrow: [],
    buy_qty: '0',
    timely_spo_qty: '0',
    revision_no: 2,
  },
  facts: {
    dealer_hot_selling: evidencedFact(false),
    project_hot_selling: evidencedFact(false),
    discontinued: false,
    days_moved: 0,
    within_reserve_window: windowFact('2027-01-10', '2027-01-10', 0),
    buy_actioned: buyActionedFact(false),
  },
  suggested: 'replan',
  why: 'Qty rose from 72 to 90; the existing 72 stays held, and only the extra 18 runs the ladder.',
  proposal: boardProposal({
    key: 'pcb-1-so400875-l3-qtyup',
    sales_order_id: 'so-400875',
    so_number: 'SO400875',
    line_no: 3,
    item_code: 'WESERP10B',
    qty: '18',
    required_date: '2027-01-10',
    reserveQty: '10',
    reserveLocation: 'BRW-BB',
    buyQty: '8',
  }),
  inquiry_rows: [{ id: 'oi-8', verb: 'ORDER', qty: '8', state: 'raised' }],
  decision: 'accept',
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO400875&cell=WESERP10B|2027-01-10',
};

const ROW_9: PlanningChangeRow = {
  id: 'pcr-9',
  line_no: 4,
  item_code: 'B2155-NL-BLUE',
  product_name: 'Basin mixer 2155 blue',
  kind: 'qty_down',
  from: { required_date: '2027-01-15', qty: '72', status: 'open' },
  to: { required_date: '2027-01-15', qty: '66', status: 'open' },
  days_moved: 0,
  held: {
    reserve: [{ location: 'BRW-BB', warehouse_id: 'wh-BRW-BB', qty: '66' }],
    borrow: [],
    buy_qty: '6',
    timely_spo_qty: '0',
    revision_no: 2,
  },
  facts: {
    dealer_hot_selling: evidencedFact(false),
    project_hot_selling: evidencedFact(false),
    discontinued: false,
    days_moved: 0,
    within_reserve_window: windowFact('2027-01-15', '2027-01-15', 0),
    buy_actioned: buyActionedFact(false),
  },
  suggested: 'reduce',
  why: 'Qty dropped from 72 to 66; the reserve of 66 stays, the Buy of 6 is reduced to nothing, and the inquiry row is cancelled for the drop.',
  proposal: null,
  inquiry_rows: [{ id: 'oi-9', verb: 'ORDER', qty: '6', state: 'raised' }],
  decision: 'accept',
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO400875&cell=B2155-NL-BLUE|2027-01-15',
};

const ROW_10: PlanningChangeRow = {
  id: 'pcr-10',
  line_no: 5,
  item_code: 'CB231SS-NL',
  product_name: 'Concealed cistern 231SS',
  kind: 'closed',
  from: { required_date: '2027-01-20', qty: '12', status: 'open' },
  to: { required_date: null, qty: null, status: 'closed' },
  days_moved: null,
  held: {
    reserve: [{ location: 'MWH-IB', warehouse_id: 'wh-MWH-IB', qty: '4' }],
    borrow: [],
    buy_qty: '8',
    timely_spo_qty: '0',
    revision_no: 2,
  },
  facts: {
    dealer_hot_selling: evidencedFact(false),
    project_hot_selling: evidencedFact(false),
    discontinued: false,
    days_moved: 0,
    within_reserve_window: windowFact('2027-01-20', '2027-01-20', 0),
    buy_actioned: buyActionedFact(true, 'PO2026-0398'),
  },
  suggested: 'retire',
  why: 'The line is closed in the book; the reserve and the remaining Buy are released, and the already-actioned inquiry row (PO2026-0398) is kept with a note rather than retired.',
  proposal: null,
  inquiry_rows: [{ id: 'oi-10', verb: 'ORDER', qty: '8', state: 'actioned' }],
  decision: 'accept',
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO400875&cell=CB231SS-NL|2027-01-20',
};

const ROW_11A: PlanningChangeRow = {
  id: 'pcr-11a',
  line_no: 9,
  item_code: 'B2155-NL-BLUE',
  product_name: 'Basin mixer 2155 blue',
  kind: 'added',
  from: { required_date: null, qty: null, status: null },
  to: { required_date: '2026-10-01', qty: '24', status: 'open' },
  days_moved: null,
  held: null,
  facts: {
    dealer_hot_selling: evidencedFact(false),
    project_hot_selling: evidencedFact(false),
    discontinued: false,
    days_moved: 0,
    within_reserve_window: windowFact('2026-10-01', '2026-10-01', 0),
    buy_actioned: buyActionedFact(false),
  },
  suggested: 'replan',
  why: 'New line on the book; nothing was ever held for it, so it simply enters the board at its new date.',
  proposal: null,
  inquiry_rows: [],
  decision: null,
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO401220&cell=B2155-NL-BLUE|2026-10-01',
};

const ROW_11B: PlanningChangeRow = {
  id: 'pcr-11b',
  line_no: 10,
  item_code: 'WESERP10B',
  product_name: 'Wall hung bidet spray',
  kind: 'added',
  from: { required_date: null, qty: null, status: null },
  to: { required_date: '2026-10-12', qty: '12', status: 'open' },
  days_moved: null,
  held: null,
  facts: {
    dealer_hot_selling: evidencedFact(false),
    project_hot_selling: evidencedFact(false),
    discontinued: false,
    days_moved: 0,
    within_reserve_window: windowFact('2026-10-12', '2026-10-12', 0),
    buy_actioned: buyActionedFact(false),
  },
  suggested: 'replan',
  why: 'New line on the book; nothing was ever held for it, so it simply enters the board at its new date.',
  proposal: null,
  inquiry_rows: [],
  decision: null,
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO401220&cell=WESERP10B|2026-10-12',
};

/** The batch under review: nothing applied yet. */
export const MOCK_PLANNING_CHANGE_BATCH_PENDING: PlanningChangeBatch = {
  id: 'pcb-1',
  created_at: '2026-08-19T08:42:00',
  created_by_name: 'Aina',
  source: {
    upload_id: 'imp-1042',
    file_name: 'JAN - DEC 2026 ORDER.xlsx',
    kind: 'so_book_upload',
    import_job_id: 'imp-job-1042',
  },
  applied_at: null,
  applied_by_name: null,
  result: null,
  orders: [
    {
      project_sales_order_id: 'pso-403765',
      so_number: 'SO403765',
      customer_name: 'BATHE CODE SDN BHD',
      project_label: 'Bathe Code HQ Retrofit',
      revision_no: 4,
      is_adopted: true,
      core_sales_order_id: 'core-403765',
      project_id: null,
      rows: [ROW_1, ROW_2, ROW_3, ROW_4, ROW_5, ROW_6],
    },
    {
      project_sales_order_id: 'pso-400875',
      so_number: 'SO400875',
      customer_name: 'MATRIX EXCELCON',
      project_label: 'Matrix Excelcon Phase 2',
      revision_no: 2,
      is_adopted: false,
      core_sales_order_id: null,
      project_id: 'proj-matrix-excelcon',
      rows: [ROW_7, ROW_8, ROW_9, ROW_10],
    },
    {
      project_sales_order_id: 'pso-401220',
      so_number: 'SO401220',
      customer_name: 'GREENFIELD DEVELOPMENT SDN BHD',
      project_label: 'Greenfield Suites Block C',
      revision_no: 1,
      is_adopted: false,
      core_sales_order_id: null,
      project_id: 'proj-greenfield-suites',
      rows: [ROW_11A, ROW_11B],
    },
  ],
};

/** A batch already applied: one order failed, one row was superseded before Apply ran. */
export const MOCK_PLANNING_CHANGE_BATCH_APPLIED: PlanningChangeBatch = {
  id: 'pcb-0',
  created_at: '2026-08-10T09:12:00',
  created_by_name: 'Ravi',
  source: {
    upload_id: 'imp-0091',
    file_name: 'JUN - DEC 2026 REVISION.xlsx',
    kind: 'so_book_upload',
    import_job_id: 'imp-job-0091',
  },
  applied_at: '2026-08-10T10:05:00',
  applied_by_name: 'Aina',
  result: {
    orders_revised: [{ so_number: 'SO398800', revision_no: 5 }],
    orders_failed: [
      {
        so_number: 'SO399120',
        reason: 'Revision 3 was confirmed on the board after this batch was built.',
      },
    ],
    inquiry_rows_changed: [{ verb: 'CANCEL_BALANCE', count: 1 }],
    lines_replanned: 1,
    lines_confirmed: 0,
    purchasing_notified: true,
    returned_to_review: [],
  },
  orders: [
    {
      project_sales_order_id: 'pso-398800',
      so_number: 'SO398800',
      customer_name: 'PRIMA CONSORTIUM SDN BHD',
      project_label: 'Prima Consortium Tower B',
      revision_no: 5,
      is_adopted: true,
      core_sales_order_id: 'core-398800',
      project_id: null,
      rows: [
        {
          id: 'pcr-a1',
          line_no: 2,
          item_code: 'CB231SS-NL',
          product_name: 'Concealed cistern 231SS',
          kind: 'delayed',
          from: { required_date: '2026-07-20', qty: '48', status: 'open' },
          to: { required_date: '2026-08-04', qty: '48', status: 'open' },
          days_moved: 15,
          held: {
            reserve: [{ location: 'BRW-BB', warehouse_id: 'wh-BRW-BB', qty: '48' }],
            borrow: [],
            buy_qty: '0',
            timely_spo_qty: '0',
            revision_no: 5,
          },
          facts: {
            dealer_hot_selling: evidencedFact(false),
            project_hot_selling: evidencedFact(false),
            discontinued: false,
            days_moved: 15,
            within_reserve_window: windowFact('2026-07-20', '2026-08-04', 15),
            buy_actioned: buyActionedFact(false),
          },
          suggested: 'keep',
          why: 'New date is 15 days out and inside the 60-day reserve window; the reserve stays put.',
          proposal: null,
          inquiry_rows: [],
          decision: 'accept',
          applied_state: 'applied',
          board_link: '/project-sales/fulfilment-planning?orders=SO398800&cell=CB231SS-NL|2026-08-04',
        },
        {
          id: 'pcr-a2',
          line_no: 3,
          item_code: 'B2155-NL-BLUE',
          product_name: 'Basin mixer 2155 blue',
          kind: 'qty_down',
          from: { required_date: '2026-08-01', qty: '30', status: 'open' },
          to: { required_date: '2026-08-01', qty: '22', status: 'open' },
          days_moved: 0,
          held: {
            reserve: [{ location: 'MWH-IB', warehouse_id: 'wh-MWH-IB', qty: '22' }],
            borrow: [],
            buy_qty: '8',
            timely_spo_qty: '0',
            revision_no: 5,
          },
          facts: {
            dealer_hot_selling: evidencedFact(false),
            project_hot_selling: evidencedFact(false),
            discontinued: false,
            days_moved: 0,
            within_reserve_window: windowFact('2026-08-01', '2026-08-01', 0),
            buy_actioned: buyActionedFact(false),
          },
          suggested: 'reduce',
          why: 'Qty dropped from 30 to 22; the reserve of 22 stays and the Buy of 8 is cancelled.',
          proposal: null,
          inquiry_rows: [{ id: 'oi-a2', verb: 'CANCEL_BALANCE', qty: '8', state: 'actioned' }],
          decision: 'accept',
          applied_state: 'applied',
          board_link: '/project-sales/fulfilment-planning?orders=SO398800&cell=B2155-NL-BLUE|2026-08-01',
        },
        {
          id: 'pcr-a3',
          line_no: 4,
          item_code: 'WESERP10B',
          product_name: 'Wall hung bidet spray',
          kind: 'delayed',
          from: { required_date: '2026-08-05', qty: '14', status: 'open' },
          to: { required_date: '2027-01-05', qty: '14', status: 'open' },
          days_moved: 153,
          held: {
            reserve: [{ location: 'MWH-IB', warehouse_id: 'wh-MWH-IB', qty: '14' }],
            borrow: [],
            buy_qty: '0',
            timely_spo_qty: '0',
            revision_no: 4,
          },
          facts: {
            dealer_hot_selling: evidencedFact(false),
            project_hot_selling: evidencedFact(false),
            discontinued: false,
            days_moved: 153,
            within_reserve_window: windowFact('2026-08-05', '2027-01-05', 153),
            buy_actioned: buyActionedFact(false),
          },
          suggested: 'release',
          why: 'New date is 153 days out, beyond the 60-day reserve window; the reserve is released back to MWH-IB.',
          proposal: null,
          inquiry_rows: [],
          decision: 'accept',
          applied_state: 'superseded',
          applied_reason:
            'The board confirmed revision 6 on this line after this batch was built, so this suggestion no longer applies.',
          board_link: '/project-sales/fulfilment-planning?orders=SO398800&cell=WESERP10B|2027-01-05',
        },
      ],
    },
    {
      project_sales_order_id: 'pso-399120',
      so_number: 'SO399120',
      customer_name: 'DELTA BUILD ENGINEERING',
      project_label: 'Delta Build Engineering HQ',
      revision_no: 2,
      is_adopted: false,
      core_sales_order_id: null,
      project_id: 'proj-delta-build-hq',
      rows: [
        {
          id: 'pcr-b1',
          line_no: 2,
          item_code: 'B2155-NL-BLUE',
          product_name: 'Basin mixer 2155 blue',
          kind: 'delayed',
          from: { required_date: '2026-07-28', qty: '20', status: 'open' },
          to: { required_date: '2026-12-20', qty: '20', status: 'open' },
          days_moved: 145,
          held: {
            reserve: [{ location: 'BRW-BB', warehouse_id: 'wh-BRW-BB', qty: '20' }],
            borrow: [],
            buy_qty: '0',
            timely_spo_qty: '0',
            revision_no: 2,
          },
          facts: {
            dealer_hot_selling: evidencedFact(false),
            project_hot_selling: evidencedFact(false),
            discontinued: false,
            days_moved: 145,
            within_reserve_window: windowFact('2026-07-28', '2026-12-20', 145),
            buy_actioned: buyActionedFact(false),
          },
          suggested: 'release',
          why: 'New date is 145 days out, beyond the 60-day reserve window; the reserve is released back to BRW-BB.',
          proposal: null,
          inquiry_rows: [],
          decision: 'accept',
          applied_state: 'failed',
          applied_reason: 'Revision 3 was confirmed on the board after this batch was built.',
          board_link: '/project-sales/fulfilment-planning?orders=SO399120&cell=B2155-NL-BLUE|2026-12-20',
        },
        {
          id: 'pcr-b2',
          line_no: 3,
          item_code: 'CB231SS-NL',
          product_name: 'Concealed cistern 231SS',
          kind: 'qty_up',
          from: { required_date: '2026-08-02', qty: '10', status: 'open' },
          to: { required_date: '2026-08-02', qty: '16', status: 'open' },
          days_moved: 0,
          held: {
            reserve: [{ location: 'BRW-BB', warehouse_id: 'wh-BRW-BB', qty: '10' }],
            borrow: [],
            buy_qty: '0',
            timely_spo_qty: '0',
            revision_no: 2,
          },
          facts: {
            dealer_hot_selling: evidencedFact(false),
            project_hot_selling: evidencedFact(false),
            discontinued: false,
            days_moved: 0,
            within_reserve_window: windowFact('2026-08-02', '2026-08-02', 0),
            buy_actioned: buyActionedFact(false),
          },
          suggested: 'replan',
          why: 'Qty rose from 10 to 16; the existing 10 stays held, and only the extra 6 runs the ladder.',
          proposal: null,
          inquiry_rows: [],
          decision: 'accept',
          applied_state: 'failed',
          applied_reason: 'Revision 3 was confirmed on the board after this batch was built.',
          board_link: '/project-sales/fulfilment-planning?orders=SO399120&cell=CB231SS-NL|2026-08-02',
        },
      ],
    },
  ],
};

/** `GET /project-sales/planning-changes` rows, newest first (AC-R10). */
export const MOCK_PLANNING_CHANGE_BATCHES: PlanningChangeBatchSummary[] = [
  {
    id: MOCK_PLANNING_CHANGE_BATCH_PENDING.id,
    created_at: MOCK_PLANNING_CHANGE_BATCH_PENDING.created_at,
    created_by_name: MOCK_PLANNING_CHANGE_BATCH_PENDING.created_by_name,
    source: MOCK_PLANNING_CHANGE_BATCH_PENDING.source,
    order_count: MOCK_PLANNING_CHANGE_BATCH_PENDING.orders.length,
    line_count: MOCK_PLANNING_CHANGE_BATCH_PENDING.orders.reduce(
      (total, order) => total + order.rows.length,
      0,
    ),
    pending_count: MOCK_PLANNING_CHANGE_BATCH_PENDING.orders.reduce(
      (total, order) =>
        total + order.rows.filter((row) => row.applied_state === 'pending').length,
      0,
    ),
    failed_count: 0,
    applied_at: null,
    applied_by_name: null,
    so_numbers: MOCK_PLANNING_CHANGE_BATCH_PENDING.orders.map((order) => order.so_number),
  },
  {
    id: MOCK_PLANNING_CHANGE_BATCH_APPLIED.id,
    created_at: MOCK_PLANNING_CHANGE_BATCH_APPLIED.created_at,
    created_by_name: MOCK_PLANNING_CHANGE_BATCH_APPLIED.created_by_name,
    source: MOCK_PLANNING_CHANGE_BATCH_APPLIED.source,
    order_count: MOCK_PLANNING_CHANGE_BATCH_APPLIED.orders.length,
    line_count: MOCK_PLANNING_CHANGE_BATCH_APPLIED.orders.reduce(
      (total, order) => total + order.rows.length,
      0,
    ),
    pending_count: 0,
    failed_count: MOCK_PLANNING_CHANGE_BATCH_APPLIED.orders.reduce(
      (total, order) =>
        total + order.rows.filter((row) => row.applied_state === 'failed').length,
      0,
    ),
    applied_at: MOCK_PLANNING_CHANGE_BATCH_APPLIED.applied_at,
    applied_by_name: MOCK_PLANNING_CHANGE_BATCH_APPLIED.applied_by_name,
    so_numbers: MOCK_PLANNING_CHANGE_BATCH_APPLIED.orders.map((order) => order.so_number),
  },
];

/**
 * Part 3's own case (`PLAN-scm-cs-planning-uat.md`, AC-P3-2): SO381895 re-uploaded with form
 * (3). SRTWCX7405-RL-S-PJ's three instalments - 10 on 25 Aug, 10 on 5 Sep, 5 on 10 Sep -
 * become one line of 25 on 19 Aug, so one row is advanced and two are closed. The closed line
 * of 10 already had its stock physically moved, which is the transfer flag.
 *
 * Every row here is the shape the board annotates a cell with, so the Was / Now table, the
 * `Closed` reading and the moved-transfer phrase are all on one fixture.
 */
export const MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE: PlanningChangeBatch = {
  id: 'pcb-so381895',
  created_at: '2026-08-19T09:23:00Z',
  created_by_name: 'Cyndi Tee',
  source: {
    upload_id: 'imp-so381895',
    file_name: 'Outstanding SO 19 Aug.xlsx',
    kind: 'so_book_upload',
    import_job_id: 'imp-so381895',
  },
  applied_at: null,
  applied_by_name: null,
  orders: [
    {
      project_sales_order_id: 'pso-381895',
      so_number: 'SO381895',
      customer_name: 'YOTU BUILDER',
      project_label: 'LOT 2752',
      revision_no: 2,
      is_adopted: true,
      core_sales_order_id: 'so-381895',
      project_id: null,
      rows: [
        {
          id: 'pcr-381895-1',
          project_line_id: 'pl-381895-1',
          line_no: 1,
          item_code: 'SRTWCX7405-RL-S-PJ',
          product_name: 'Floor trap 7405 RL S',
          kind: 'advanced',
          from: { required_date: '2026-08-25', qty: '10', status: 'open' },
          to: { required_date: '2026-08-19', qty: '25', status: 'open' },
          days_moved: -6,
          held: { reserve: [], borrow: [], buy_qty: '10', timely_spo_qty: '0', revision_no: 2 },
          facts: {
            dealer_hot_selling: evidencedFact(false),
            project_hot_selling: evidencedFact(false),
            discontinued: false,
            days_moved: -6,
            within_reserve_window: windowFact('2026-08-25', '2026-08-19', -6),
            buy_actioned: buyActionedFact(false),
          },
          suggested: 'replan',
          why: 'Advanced 6 days; the line runs the ladder again at the new date now.',
          proposal: boardProposal({
            key: 'SO381895|1|SRTWCX7405-RL-S-PJ',
            sales_order_id: 'so-381895',
            so_number: 'SO381895',
            line_no: 1,
            item_code: 'SRTWCX7405-RL-S-PJ',
            qty: '25',
            required_date: '2026-08-19',
            reserveQty: '0',
            reserveLocation: 'BRW-IB',
            buyQty: '25',
          }),
          inquiry_rows: [{ id: 'oir-1', verb: 'ORDER', qty: '10', state: 'placed' }],
          decision: null,
          applied_state: 'pending',
          board_link:
            '/project-sales/fulfilment-planning?orders=SO381895&cell=SRTWCX7405-RL-S-PJ|2026-08-19',
        },
        {
          id: 'pcr-381895-2',
          project_line_id: 'pl-381895-2',
          line_no: 2,
          item_code: 'SRTWCX7405-RL-S-PJ',
          product_name: 'Floor trap 7405 RL S',
          kind: 'closed',
          from: { required_date: '2026-09-05', qty: '10', status: 'open' },
          to: { required_date: null, qty: null, status: 'closed' },
          days_moved: null,
          held: { reserve: [], borrow: [], buy_qty: '10', timely_spo_qty: '0', revision_no: 2 },
          facts: {
            dealer_hot_selling: evidencedFact(false),
            project_hot_selling: evidencedFact(false),
            discontinued: false,
            days_moved: 0,
            within_reserve_window: windowFact('2026-09-05', '2026-09-05', 0),
            buy_actioned: buyActionedFact(false),
          },
          suggested: 'retire',
          why: 'The line is closed in the book.',
          proposal: null,
          inquiry_rows: [{ id: 'oir-2', verb: 'ORDER', qty: '10', state: 'placed' }],
          decision: 'accept',
          applied_state: 'pending',
          moved_transfer: '10 moved BRW -> BRW-IB, line cancelled',
          board_link:
            '/project-sales/fulfilment-planning?orders=SO381895&cell=SRTWCX7405-RL-S-PJ|2026-09-05',
        },
        {
          id: 'pcr-381895-3',
          project_line_id: 'pl-381895-3',
          line_no: 3,
          item_code: 'SRTWCX7405-RL-S-PJ',
          product_name: 'Floor trap 7405 RL S',
          kind: 'closed',
          from: { required_date: '2026-09-10', qty: '5', status: 'open' },
          to: { required_date: null, qty: null, status: 'closed' },
          days_moved: null,
          held: { reserve: [], borrow: [], buy_qty: '5', timely_spo_qty: '0', revision_no: 2 },
          facts: {
            dealer_hot_selling: evidencedFact(false),
            project_hot_selling: evidencedFact(false),
            discontinued: false,
            days_moved: 0,
            within_reserve_window: windowFact('2026-09-10', '2026-09-10', 0),
            buy_actioned: buyActionedFact(false),
          },
          suggested: 'retire',
          why: 'The line is closed in the book.',
          proposal: null,
          inquiry_rows: [{ id: 'oir-3', verb: 'ORDER', qty: '5', state: 'raised' }],
          decision: 'accept',
          applied_state: 'pending',
          board_link:
            '/project-sales/fulfilment-planning?orders=SO381895&cell=SRTWCX7405-RL-S-PJ|2026-09-10',
        },
      ],
    },
  ],
};
