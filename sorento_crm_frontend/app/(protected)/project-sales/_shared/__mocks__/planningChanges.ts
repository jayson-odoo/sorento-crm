/**
 * Phase 1 fixtures for planning changes
 * (`documentation/plans/scm/PLAN-scm-change-management-one-engine.md`, Slice C contract).
 *
 * `pcb-1` is the batch under review: ONE ROW PER SCENARIO S1 to S12 of
 * `documentation/plans/scm/mockups/so-change-management-grill-v4.html`, carrying the exact
 * suggestion lines that page gives, spread across three planned orders so every render state
 * (held, no hold, dealer hot-selling, buy-actioned, advance, qty up, qty down, cancelled,
 * added, product changed, late, short) is on screen at once. One order is adopted (mirror of
 * the AutoCount book, SO403765) and two are authored project SOs, so the SO-number link covers
 * both kinds. `pcb-0` is a batch already applied, carrying the two safety states Apply can
 * leave behind (one order that failed, one row a later board edit superseded before Apply ran)
 * plus the `result` Apply wrote.
 *
 * Kept after the backend landed because the component tests read from it: one shape for the
 * prototype and the tests means a test cannot pass against a row the screen never saw.
 */
import type {
  BoardContribution,
  BoardTrailStep,
  ConfirmLine,
} from '../types/fulfilmentPlanning.types';
import type {
  PlanningChangeBatch,
  PlanningChangeBatchSummary,
  PlanningChangeBuyActionedFact,
  PlanningChangeEvidencedFact,
  PlanningChangeHeld,
  PlanningChangePlacedFact,
  PlanningChangeRow,
} from '../types/planningChange.types';

/** A fact with no supporting evidence - `dealer_hot_selling: false` needs no `where`. */
function evidencedFact(value: boolean, where: string[] = []): PlanningChangeEvidencedFact {
  return { value, where };
}

/**
 * What is already ON a document for this line, and when it lands (S2, S12).
 *
 * `within_reserve_window` used to sit beside this; Slice C retired it (rule 2) - the
 * ladder's own step 0 decides whether a line that far out may hold stock.
 */
function placedFact(
  qty = '0',
  document: string | null = null,
  arrivalDate: string | null = null,
): PlanningChangePlacedFact {
  return { qty, document, arrival_date: arrivalDate };
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
      kind: 'own',
      question: 'Can we use our location?',
      answer: 'yes',
      took: reserveQty,
      from: reserveLocation,
      location: reserveLocation,
      warehouse_id: `wh-${reserveLocation}`,
      ahead_qty: '0',
      ahead_lines: 0,
      ahead: [],
      ahead_more: 0,
      why: `The BB group nets ${reserveQty}, leaving ${reserveQty} for this line; it was drawn at ${reserveLocation}.`,
    },
    {
      step: 2,
      kind: 'pool',
      question: 'Can we take from the pool?',
      answer: 'no',
      took: '0',
      note: 'no shared pool',
      why: 'No shared pool holds this product.',
    },
    {
      step: 3,
      kind: 'cross_group_borrow',
      question: 'Can we borrow from another location?',
      answer: 'no',
      took: '0',
      why: 'No location outside this ownership group holds any of this item.',
    },
    {
      step: 4,
      kind: 'group_borrow',
      question: "Can we borrow from the same agent's other order in this group?",
      answer: 'no',
      took: '0',
      why:
        'No other sales order in this ownership group holds any of this item, so there is ' +
        "nothing to borrow from a person's pick either.",
    },
    {
      step: 5,
      kind: 'buy',
      question: 'Buy the rest?',
      answer: buyQty === '0' ? 'no' : 'yes',
      took: buyQty,
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

/** What a line's active decision holds today, spelled the short way for a fixture. */
function heldOf(over: {
  reserve?: { location: string; qty: string }[];
  borrow?: { location: string; qty: string; source?: string }[];
  buy?: string;
  spo?: string;
  revisionNo?: number;
}): PlanningChangeHeld {
  return {
    reserve: (over.reserve ?? []).map((entry) => ({
      location: entry.location,
      warehouse_id: `wh-${entry.location}`,
      qty: entry.qty,
    })),
    borrow: (over.borrow ?? []).map((entry) => ({
      location: entry.location,
      warehouse_id: `wh-${entry.location}`,
      qty: entry.qty,
      source: entry.source ?? 'other_location',
    })),
    buy_qty: over.buy ?? '0',
    timely_spo_qty: over.spo ?? '0',
    revision_no: over.revisionNo ?? 4,
  };
}

/**
 * What Apply posts for the row: PRE-FILLED at build from the re-run (Slice C contract A), so
 * Confirm posts it unchanged and Amend opens the board's own dialog on it.
 */
function compositionOf(over: {
  lineId: string;
  reserve?: { location: string; qty: string }[];
  borrow?: {
    location: string;
    qty: string;
    donorSoNumber?: string;
    donorLineNo?: number;
  }[];
  buy?: string;
  spo?: string;
}): ConfirmLine {
  return {
    project_line_id: over.lineId,
    timely_spo_qty: over.spo ?? '0',
    reserve: (over.reserve ?? []).map((entry) => ({
      warehouse_id: `wh-${entry.location}`,
      qty: entry.qty,
    })),
    borrow: (over.borrow ?? []).map((entry) => ({
      source: 'other_location' as const,
      warehouse_id: `wh-${entry.location}`,
      qty: entry.qty,
      reason: entry.donorSoNumber
        ? `${entry.donorSoNumber} holds the whole unit on hand and is due later.`
        : 'The whole unit is on hand at another location.',
      donor_so_number: entry.donorSoNumber ?? null,
      donor_line_no: entry.donorLineNo ?? null,
    })),
    buy_qty: over.buy ?? '0',
  };
}

/**
 * S1 (AC-B1). Qty up 134 -> 234 on a Buy the line already holds, due outside the immediate
 * window: the top-up JOINS the held Buy on the same inquiry row rather than splitting the
 * unit into stock plus a purchase.
 */
const ROW_S1: PlanningChangeRow = {
  id: 'pcr-s1',
  project_line_id: 'pl-403765-3',
  line_no: 3,
  item_code: 'B2155-NL-BLUE',
  product_name: 'Basin mixer 2155 blue',
  kind: 'qty_up',
  from: { required_date: '2026-09-04', qty: '134', status: 'open' },
  to: { required_date: '2026-09-04', qty: '234', status: 'open' },
  days_moved: 0,
  held: heldOf({ buy: '134' }),
  facts: {
    dealer_hot_selling: evidencedFact(false),
    project_hot_selling: evidencedFact(false),
    discontinued: false,
    days_moved: 0,
    buy_actioned: buyActionedFact(false),
    placed: placedFact(),
  },
  suggestion: {
    components: [
      {
        action: 'buy',
        source: 'buy',
        qty_was: '134',
        qty_now: '234',
        label: 'Buy 234 (was 134)',
      },
    ],
  },
  proposal: boardProposal({
    key: 'pcb-1-so403765-l3-qtyup',
    sales_order_id: 'so-403765',
    so_number: 'SO403765',
    line_no: 3,
    item_code: 'B2155-NL-BLUE',
    qty: '234',
    required_date: '2026-09-04',
    reserveQty: '0',
    reserveLocation: 'BRW-IB',
    buyQty: '234',
  }),
  inquiry_rows: [{ id: 'oi-s1', verb: 'ORDER', qty: '134', state: 'raised' }],
  decision: 'confirm',
  composition: compositionOf({ lineId: 'pl-403765-3', buy: '234' }),
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO403765&cell=B2155-NL-BLUE|2026-09-04',
};

/**
 * S2 (AC-C4). Qty down 234 -> 100 with 134 already placed on PO-A and 100 still raised: the
 * unplaced row is reduced first, the placed one is kept down to what is still needed, and the
 * freed 34 of PO-A is re-dealt to an inquiry row that wants it (not dealer hot-selling here,
 * so the dealer pool does not take it).
 */
const ROW_S2: PlanningChangeRow = {
  id: 'pcr-s2',
  project_line_id: 'pl-403765-4',
  line_no: 4,
  item_code: 'B2155-NL-BLUE',
  product_name: 'Basin mixer 2155 blue',
  kind: 'qty_down',
  from: { required_date: '2026-09-04', qty: '234', status: 'open' },
  to: { required_date: '2026-09-04', qty: '100', status: 'open' },
  days_moved: 0,
  held: heldOf({ buy: '234' }),
  facts: {
    dealer_hot_selling: evidencedFact(false),
    project_hot_selling: evidencedFact(false),
    discontinued: false,
    days_moved: 0,
    buy_actioned: buyActionedFact(true, 'PO-A'),
    placed: placedFact('134', 'PO-A', '2026-10-01'),
  },
  suggestion: {
    components: [
      {
        action: 'reduce',
        source: 'buy',
        qty_was: '100',
        qty_now: '0',
        label: 'Reduce Buy 100 to 0',
      },
      {
        action: 'keep',
        source: 'po',
        qty_was: '134',
        qty_now: '100',
        document: 'PO-A',
        label: 'Keep PO-A 100 of 134',
      },
      {
        action: 'reallocate',
        source: 'po',
        qty_now: '34',
        document: 'PO-A',
        target: 'SO420103 ORDER 50',
        label: 'Reallocate PO-A 34 to SO420103 ORDER 50',
      },
    ],
  },
  proposal: null,
  inquiry_rows: [
    { id: 'oi-s2a', verb: 'ORDER', qty: '134', state: 'placed' },
    { id: 'oi-s2b', verb: 'ORDER', qty: '100', state: 'raised' },
  ],
  decision: 'confirm',
  composition: compositionOf({ lineId: 'pl-403765-4', buy: '100' }),
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO403765&cell=B2155-NL-BLUE|2026-09-04',
};

/**
 * S3 (AC-D4). Delayed inside the reserve window, but another order's raised row needs the
 * stock EARLIER: 80 of the reserve moves to it, the rest is freed, and this line is re-sourced
 * whole for its new date off an SPO that lands in time.
 */
const ROW_S3: PlanningChangeRow = {
  id: 'pcr-s3',
  project_line_id: 'pl-403765-5',
  line_no: 5,
  item_code: 'B2155-NL-BLUE',
  product_name: 'Basin mixer 2155 blue',
  kind: 'delayed',
  from: { required_date: '2026-09-04', qty: '134', status: 'open' },
  to: { required_date: '2026-11-20', qty: '134', status: 'open' },
  days_moved: 77,
  held: heldOf({ reserve: [{ location: 'BRW-IB', qty: '134' }] }),
  facts: {
    dealer_hot_selling: evidencedFact(false),
    project_hot_selling: evidencedFact(false),
    discontinued: false,
    days_moved: 77,
    buy_actioned: buyActionedFact(false),
    placed: placedFact(),
  },
  suggestion: {
    components: [
      {
        action: 'reallocate',
        source: 'reserve',
        qty_now: '80',
        location: 'BRW-IB',
        target: 'SO420100 ORDER 80',
        label: 'Reallocate 80 at BRW-IB to SO420100 ORDER 80',
      },
      {
        action: 'release',
        source: 'reserve',
        qty_now: '54',
        location: 'BRW-IB',
        label: 'Release 54, free at BRW-IB',
      },
      {
        action: 'spo',
        source: 'spo',
        qty_now: '134',
        document: 'SPO-77',
        label: 'SPO 134 on SPO-77 for 20 Nov',
      },
    ],
  },
  proposal: null,
  inquiry_rows: [],
  decision: null,
  composition: compositionOf({ lineId: 'pl-403765-5', spo: '134' }),
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO403765&cell=B2155-NL-BLUE|2026-11-20',
};

/**
 * S4. Advanced past what PO-A can land: no half measures, so the whole unit is borrowed from
 * a later order that holds it on hand, and PO-A follows to that order's own order-back row.
 */
const ROW_S4: PlanningChangeRow = {
  id: 'pcr-s4',
  project_line_id: 'pl-403765-6',
  line_no: 6,
  item_code: 'B2155-NL-BLUE',
  product_name: 'Basin mixer 2155 blue',
  kind: 'advanced',
  from: { required_date: '2026-09-04', qty: '134', status: 'open' },
  to: { required_date: '2026-08-20', qty: '134', status: 'open' },
  days_moved: -15,
  held: heldOf({ buy: '134' }),
  facts: {
    dealer_hot_selling: evidencedFact(false),
    project_hot_selling: evidencedFact(false),
    discontinued: false,
    days_moved: -15,
    buy_actioned: buyActionedFact(true, 'PO-A'),
    placed: placedFact('134', 'PO-A', '2026-09-01'),
  },
  suggestion: {
    components: [
      {
        action: 'reallocate',
        source: 'po',
        qty_now: '134',
        document: 'PO-A',
        target: 'SO419900 ORDER BACK 134',
        label: 'Reallocate PO-A 134 to SO419900 ORDER BACK 134',
      },
      {
        action: 'borrow',
        source: 'borrow',
        qty_now: '134',
        location: 'BRW-IB',
        target: 'SO419900',
        label: 'Borrow 134 from SO419900, order-back raised',
      },
    ],
  },
  proposal: null,
  inquiry_rows: [{ id: 'oi-s4', verb: 'ORDER', qty: '134', state: 'placed' }],
  decision: 'amend',
  composition: compositionOf({
    lineId: 'pl-403765-6',
    borrow: [{ location: 'BRW-IB', qty: '134', donorSoNumber: 'SO419900', donorLineNo: 2 }],
  }),
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO403765&cell=B2155-NL-BLUE|2026-08-20',
};

/**
 * S5 (AC-C5). The line is cancelled: every held component leaves it - the reserve is freed and
 * the placed PO-B quantity goes to the dealer pool, because the product IS dealer hot-selling
 * and retail wins over a waiting project row (grill page, decided 3.1).
 */
const ROW_S5: PlanningChangeRow = {
  id: 'pcr-s5',
  project_line_id: 'pl-403765-7',
  line_no: 7,
  item_code: 'B2155-NL-BLUE',
  product_name: 'Basin mixer 2155 blue',
  kind: 'cancelled',
  from: { required_date: '2026-09-04', qty: '134', status: 'open' },
  to: { required_date: null, qty: null, status: 'closed' },
  days_moved: null,
  held: heldOf({ reserve: [{ location: 'BRW-IB', qty: '50' }], buy: '84' }),
  facts: {
    dealer_hot_selling: evidencedFact(true, ['BRW', 'BRW-IB']),
    project_hot_selling: evidencedFact(false),
    discontinued: false,
    days_moved: 0,
    buy_actioned: buyActionedFact(true, 'PO-B'),
    placed: placedFact('84', 'PO-B', '2026-10-08'),
  },
  suggestion: {
    components: [
      {
        action: 'release',
        source: 'reserve',
        qty_now: '50',
        location: 'BRW-IB',
        target: 'dealer pool',
        label: 'Release 50 to dealer pool',
      },
      {
        action: 'reallocate',
        source: 'po',
        qty_now: '84',
        document: 'PO-B',
        target: 'dealer pool',
        label: 'Reallocate PO-B 84 to dealer pool',
      },
    ],
  },
  proposal: null,
  inquiry_rows: [{ id: 'oi-s5', verb: 'ORDER', qty: '84', state: 'placed' }],
  decision: 'confirm',
  composition: null,
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO403765&cell=B2155-NL-BLUE|2026-09-04',
};

/**
 * S6. A new line on an order that already has held lines: nothing to diff against, so the
 * suggestion is new sourcing only, one step for the whole 60.
 */
const ROW_S6: PlanningChangeRow = {
  id: 'pcr-s6',
  project_line_id: null,
  line_no: 8,
  item_code: 'B2160-NL-BLUE',
  product_name: 'Basin mixer 2160 blue',
  kind: 'added',
  from: { required_date: null, qty: null, status: null },
  to: { required_date: '2026-09-04', qty: '60', status: 'open' },
  days_moved: null,
  held: null,
  facts: {
    dealer_hot_selling: evidencedFact(false),
    project_hot_selling: evidencedFact(false),
    discontinued: false,
    days_moved: 0,
    buy_actioned: buyActionedFact(false),
    placed: placedFact(),
  },
  suggestion: {
    components: [
      {
        action: 'use_own',
        source: 'reserve',
        qty_now: '60',
        location: 'BRW-IB',
        label: 'Use own 60 at BRW-IB',
      },
    ],
  },
  proposal: null,
  inquiry_rows: [],
  decision: null,
  composition: null,
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO403765&cell=B2160-NL-BLUE|2026-09-04',
};

/**
 * S7 (AC-C5). One product swapped for another on the SAME line: ONE row, never a cancelled
 * plus an added pair. The old product's hold leaves it; the new product is sourced as a new
 * line in the same row.
 */
const ROW_S7: PlanningChangeRow = {
  id: 'pcr-s7',
  project_line_id: 'pl-400875-2',
  line_no: 2,
  item_code: 'B2155-NL-WHITE',
  product_name: 'Basin mixer 2155 white',
  kind: 'product_changed',
  from: {
    required_date: '2026-09-04',
    qty: '134',
    status: 'open',
    item_code: 'B2155-NL-BLUE',
  },
  to: {
    required_date: '2026-09-04',
    qty: '134',
    status: 'open',
    item_code: 'B2155-NL-WHITE',
  },
  days_moved: 0,
  held: heldOf({ reserve: [{ location: 'BRW-IB', qty: '134' }] }),
  facts: {
    dealer_hot_selling: evidencedFact(false),
    project_hot_selling: evidencedFact(false),
    discontinued: false,
    days_moved: 0,
    buy_actioned: buyActionedFact(false),
    placed: placedFact(),
  },
  suggestion: {
    components: [
      {
        action: 'release',
        source: 'reserve',
        qty_now: '134',
        location: 'BRW-IB',
        label: 'Release 134, free at BRW-IB',
      },
      {
        action: 'buy',
        source: 'buy',
        qty_now: '134',
        item_code: 'B2155-NL-WHITE',
        label: 'Buy 134 for 4 Sep',
      },
    ],
  },
  proposal: null,
  inquiry_rows: [],
  decision: null,
  composition: compositionOf({ lineId: 'pl-400875-2', buy: '134' }),
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO400875&cell=B2155-NL-WHITE|2026-09-04',
};

/**
 * S8 (AC-C8). A date AND a quantity in one edit: ONE row, one run at (100, 20 Nov), one
 * composed suggestion. No tie-break decides which half of the edit "wins".
 */
const ROW_S8: PlanningChangeRow = {
  id: 'pcr-s8',
  project_line_id: 'pl-400875-3',
  line_no: 3,
  item_code: 'B2155-NL-BLUE',
  product_name: 'Basin mixer 2155 blue',
  kind: 'qty_down',
  from: { required_date: '2026-09-04', qty: '134', status: 'open' },
  to: { required_date: '2026-11-20', qty: '100', status: 'open' },
  days_moved: 77,
  held: heldOf({ reserve: [{ location: 'BRW-IB', qty: '134' }] }),
  facts: {
    dealer_hot_selling: evidencedFact(false),
    project_hot_selling: evidencedFact(false),
    discontinued: false,
    days_moved: 77,
    buy_actioned: buyActionedFact(false),
    placed: placedFact(),
  },
  suggestion: {
    components: [
      {
        action: 'reduce',
        source: 'reserve',
        qty_was: '134',
        qty_now: '100',
        location: 'BRW-IB',
        label: 'Reduce reserve 134 to 100',
      },
    ],
  },
  proposal: null,
  inquiry_rows: [],
  decision: 'confirm',
  composition: compositionOf({
    lineId: 'pl-400875-3',
    reserve: [{ location: 'BRW-IB', qty: '100' }],
  }),
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO400875&cell=B2155-NL-BLUE|2026-11-20',
};

/**
 * S9 (AC-C2). A small delay, still inside the reserve window, and no inquiry row wants the
 * stock earlier: Keep, and nothing else. One line is the whole suggestion.
 */
const ROW_S9: PlanningChangeRow = {
  id: 'pcr-s9',
  project_line_id: 'pl-400875-4',
  line_no: 4,
  item_code: 'B2155-NL-BLUE',
  product_name: 'Basin mixer 2155 blue',
  kind: 'delayed',
  from: { required_date: '2026-09-04', qty: '134', status: 'open' },
  to: { required_date: '2026-09-25', qty: '134', status: 'open' },
  days_moved: 21,
  held: heldOf({ reserve: [{ location: 'BRW-IB', qty: '134' }] }),
  facts: {
    dealer_hot_selling: evidencedFact(false),
    project_hot_selling: evidencedFact(false),
    discontinued: false,
    days_moved: 21,
    buy_actioned: buyActionedFact(false),
    placed: placedFact(),
  },
  suggestion: {
    components: [
      {
        action: 'keep',
        source: 'reserve',
        qty_now: '134',
        location: 'BRW-IB',
        label: 'Keep 134',
      },
    ],
  },
  proposal: null,
  inquiry_rows: [],
  decision: 'confirm',
  composition: compositionOf({
    lineId: 'pl-400875-4',
    reserve: [{ location: 'BRW-IB', qty: '134' }],
  }),
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO400875&cell=B2155-NL-BLUE|2026-09-25',
};

/**
 * S10 (AC-C3). A delay past the reserve window: step 0 fires, so no stock is held for a line
 * that far out - the reserve is freed and the whole unit is bought for its own date. Keeping
 * it is available as an Amend, never as the suggestion.
 */
const ROW_S10: PlanningChangeRow = {
  id: 'pcr-s10',
  project_line_id: 'pl-400875-5',
  line_no: 5,
  item_code: 'B2155-NL-BLUE',
  product_name: 'Basin mixer 2155 blue',
  kind: 'delayed',
  from: { required_date: '2026-09-04', qty: '134', status: 'open' },
  to: { required_date: '2027-03-15', qty: '134', status: 'open' },
  days_moved: 192,
  held: heldOf({ reserve: [{ location: 'BRW-IB', qty: '134' }] }),
  facts: {
    dealer_hot_selling: evidencedFact(false),
    project_hot_selling: evidencedFact(false),
    discontinued: false,
    days_moved: 192,
    buy_actioned: buyActionedFact(false),
    placed: placedFact(),
  },
  suggestion: {
    components: [
      {
        action: 'release',
        source: 'reserve',
        qty_now: '134',
        location: 'BRW-IB',
        label: 'Release 134, free at BRW-IB',
      },
      {
        action: 'buy',
        source: 'buy',
        qty_now: '134',
        label: 'Buy 134 for 15 Mar',
      },
    ],
  },
  proposal: null,
  inquiry_rows: [],
  decision: null,
  composition: compositionOf({ lineId: 'pl-400875-5', buy: '134' }),
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO400875&cell=B2155-NL-BLUE|2027-03-15',
};

/**
 * S11 (AC-B3). Advanced INTO the immediate window, where the pool-share step may cover PART
 * of the unit: 90 from the pool now, the held Buy reduced to the 44 left, and nothing can
 * cover that 44 in time - so the board says so rather than promising a date.
 */
const ROW_S11: PlanningChangeRow = {
  id: 'pcr-s11',
  project_line_id: 'pl-401220-2',
  line_no: 2,
  item_code: 'B2155-NL-BLUE',
  product_name: 'Basin mixer 2155 blue',
  kind: 'advanced',
  from: { required_date: '2026-09-04', qty: '134', status: 'open' },
  to: { required_date: '2026-08-22', qty: '134', status: 'open' },
  days_moved: -13,
  held: heldOf({ buy: '134' }),
  facts: {
    dealer_hot_selling: evidencedFact(false),
    project_hot_selling: evidencedFact(false),
    discontinued: false,
    days_moved: -13,
    buy_actioned: buyActionedFact(false),
    placed: placedFact(),
  },
  suggestion: {
    components: [
      {
        action: 'buy',
        source: 'buy',
        qty_was: '134',
        qty_now: '44',
        label: 'Short 44 by 22 Aug',
      },
      {
        action: 'use_own',
        source: 'pool_share',
        qty_now: '90',
        location: 'BRW',
        label: 'Pool share 90 at BRW',
      },
    ],
    shortfall_qty: '44',
  },
  proposal: boardProposal({
    key: 'pcb-1-so401220-l2-advance',
    sales_order_id: 'so-401220',
    so_number: 'SO401220',
    line_no: 2,
    item_code: 'B2155-NL-BLUE',
    qty: '134',
    required_date: '2026-08-22',
    reserveQty: '90',
    reserveLocation: 'BRW',
    buyQty: '44',
  }),
  inquiry_rows: [{ id: 'oi-s11', verb: 'ORDER', qty: '134', state: 'raised' }],
  decision: null,
  composition: compositionOf({
    lineId: 'pl-401220-2',
    reserve: [{ location: 'BRW', qty: '90' }],
    buy: '44',
  }),
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO401220&cell=B2155-NL-BLUE|2026-08-22',
};

/**
 * S12 (AC-C6). Advanced, but PO-A lands three days after the new date and no donor can lend
 * the whole unit: the plan stands and the lateness is SAID, so CS can amend or push the PO
 * date outside the system. A unit kept late is never silently kept.
 */
const ROW_S12: PlanningChangeRow = {
  id: 'pcr-s12',
  project_line_id: 'pl-401220-3',
  line_no: 3,
  item_code: 'B2155-NL-BLUE',
  product_name: 'Basin mixer 2155 blue',
  kind: 'advanced',
  from: { required_date: '2026-09-04', qty: '134', status: 'open' },
  to: { required_date: '2026-08-25', qty: '134', status: 'open' },
  days_moved: -10,
  held: heldOf({ buy: '134' }),
  facts: {
    dealer_hot_selling: evidencedFact(false),
    project_hot_selling: evidencedFact(false),
    discontinued: false,
    days_moved: -10,
    buy_actioned: buyActionedFact(true, 'PO-A'),
    placed: placedFact('134', 'PO-A', '2026-08-28'),
  },
  suggestion: {
    components: [
      {
        action: 'keep',
        source: 'po',
        qty_now: '134',
        document: 'PO-A',
        label: 'Keep 134, late by 3 days',
      },
    ],
    late_days: 3,
  },
  proposal: null,
  inquiry_rows: [{ id: 'oi-s12', verb: 'ORDER', qty: '134', state: 'placed' }],
  decision: 'confirm',
  composition: compositionOf({ lineId: 'pl-401220-3', buy: '134' }),
  applied_state: 'pending',
  board_link: '/project-sales/fulfilment-planning?orders=SO401220&cell=B2155-NL-BLUE|2026-08-25',
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
      rows: [ROW_S1, ROW_S2, ROW_S3, ROW_S4, ROW_S5, ROW_S6],
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
      rows: [ROW_S7, ROW_S8, ROW_S9, ROW_S10],
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
      rows: [ROW_S11, ROW_S12],
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
            buy_actioned: buyActionedFact(false),
            placed: placedFact(),
          },
          suggestion: {
            components: [
              {
                action: 'keep',
                source: 'reserve',
                qty_now: '48',
                location: 'BRW-BB',
                label: 'Keep 48',
              },
            ],
          },
          proposal: null,
          inquiry_rows: [],
          decision: 'confirm',
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
            buy_actioned: buyActionedFact(false),
            placed: placedFact(),
          },
          suggestion: {
            components: [
              {
                action: 'keep',
                source: 'reserve',
                qty_now: '22',
                location: 'MWH-IB',
                label: 'Keep 22',
              },
              {
                action: 'reduce',
                source: 'buy',
                qty_was: '8',
                qty_now: '0',
                label: 'Reduce Buy 8 to 0',
              },
            ],
          },
          proposal: null,
          inquiry_rows: [{ id: 'oi-a2', verb: 'CANCEL_BALANCE', qty: '8', state: 'actioned' }],
          decision: 'confirm',
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
            buy_actioned: buyActionedFact(false),
            placed: placedFact(),
          },
          suggestion: {
            components: [
              {
                action: 'release',
                source: 'reserve',
                qty_now: '14',
                location: 'MWH-IB',
                label: 'Release 14, free at MWH-IB',
              },
              { action: 'buy', source: 'buy', qty_now: '14', label: 'Buy 14 for 5 Jan' },
            ],
          },
          proposal: null,
          inquiry_rows: [],
          decision: 'confirm',
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
            buy_actioned: buyActionedFact(false),
            placed: placedFact(),
          },
          suggestion: {
            components: [
              {
                action: 'release',
                source: 'reserve',
                qty_now: '20',
                location: 'BRW-BB',
                label: 'Release 20, free at BRW-BB',
              },
              { action: 'buy', source: 'buy', qty_now: '20', label: 'Buy 20 for 20 Dec' },
            ],
          },
          proposal: null,
          inquiry_rows: [],
          decision: 'confirm',
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
            buy_actioned: buyActionedFact(false),
            placed: placedFact(),
          },
          suggestion: {
            components: [
              {
                action: 'keep',
                source: 'reserve',
                qty_now: '10',
                location: 'BRW-BB',
                label: 'Keep 10',
              },
              { action: 'buy', source: 'buy', qty_now: '6', label: 'Buy 6 for 2 Aug' },
            ],
          },
          proposal: null,
          inquiry_rows: [],
          decision: 'confirm',
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
 * A second pending batch, on a DIFFERENT `so_number` from `MOCK_PLANNING_CHANGE_BATCH_SO_
 * CHANGE`, for `PLAN-scm-board-picks-up-pending-change.md` (AC-B3: two orders on the board,
 * each with its own pending batch). One order, one row, so the two-batch board tests stay
 * about the union rather than about a second copy of the first fixture's shape.
 */
export const MOCK_PLANNING_CHANGE_BATCH_SO_CHANGE_2: PlanningChangeBatch = {
  id: 'pcb-so381896',
  created_at: '2026-08-19T09:30:00Z',
  created_by_name: 'Cyndi Tee',
  source: {
    upload_id: 'imp-so381896',
    file_name: 'Outstanding SO 19 Aug.xlsx',
    kind: 'so_book_upload',
    import_job_id: 'imp-so381896',
  },
  applied_at: null,
  applied_by_name: null,
  orders: [
    {
      project_sales_order_id: 'pso-381896',
      so_number: 'SO381896',
      customer_name: 'BATHE CODE SDN BHD',
      project_label: 'Bathe Code HQ Retrofit',
      revision_no: 1,
      is_adopted: true,
      core_sales_order_id: 'so-381896',
      project_id: null,
      rows: [
        {
          id: 'pcr-381896-1',
          project_line_id: 'pl-381896-1',
          line_no: 1,
          item_code: 'CB231SS-NL',
          product_name: 'Concealed cistern 231SS',
          kind: 'delayed',
          from: { required_date: '2026-08-20', qty: '15', status: 'open' },
          to: { required_date: '2026-09-03', qty: '15', status: 'open' },
          days_moved: 14,
          held: { reserve: [], borrow: [], buy_qty: '15', timely_spo_qty: '0', revision_no: 1 },
          facts: {
            dealer_hot_selling: evidencedFact(false),
            project_hot_selling: evidencedFact(false),
            discontinued: false,
            days_moved: 14,
            buy_actioned: buyActionedFact(false),
            placed: placedFact(),
          },
          suggestion: {
            components: [
              { action: 'keep', source: 'buy', qty_now: '15', label: 'Keep Buy 15' },
            ],
          },
          proposal: null,
          inquiry_rows: [{ id: 'oir-381896-1', verb: 'ORDER', qty: '15', state: 'raised' }],
          decision: 'confirm',
          applied_state: 'pending',
          board_link:
            '/project-sales/fulfilment-planning?orders=SO381896&cell=CB231SS-NL|2026-09-03',
        },
      ],
    },
  ],
};

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
            buy_actioned: buyActionedFact(false),
            placed: placedFact(),
          },
          suggestion: {
            components: [
              {
                action: 'buy',
                source: 'buy',
                qty_was: '10',
                qty_now: '25',
                label: 'Buy 25 (was 10)',
              },
            ],
          },
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
          kind: 'cancelled',
          from: { required_date: '2026-09-05', qty: '10', status: 'open' },
          to: { required_date: null, qty: null, status: 'closed' },
          days_moved: null,
          held: { reserve: [], borrow: [], buy_qty: '10', timely_spo_qty: '0', revision_no: 2 },
          facts: {
            dealer_hot_selling: evidencedFact(false),
            project_hot_selling: evidencedFact(false),
            discontinued: false,
            days_moved: 0,
            buy_actioned: buyActionedFact(false),
            placed: placedFact(),
          },
          suggestion: {
            components: [
              {
                action: 'release',
                source: 'buy',
                qty_was: '10',
                qty_now: '0',
                label: 'Release Buy 10, line cancelled',
              },
            ],
          },
          proposal: null,
          inquiry_rows: [{ id: 'oir-2', verb: 'ORDER', qty: '10', state: 'placed' }],
          decision: 'confirm',
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
          kind: 'cancelled',
          from: { required_date: '2026-09-10', qty: '5', status: 'open' },
          to: { required_date: null, qty: null, status: 'closed' },
          days_moved: null,
          held: { reserve: [], borrow: [], buy_qty: '5', timely_spo_qty: '0', revision_no: 2 },
          facts: {
            dealer_hot_selling: evidencedFact(false),
            project_hot_selling: evidencedFact(false),
            discontinued: false,
            days_moved: 0,
            buy_actioned: buyActionedFact(false),
            placed: placedFact(),
          },
          suggestion: {
            components: [
              {
                action: 'release',
                source: 'buy',
                qty_was: '5',
                qty_now: '0',
                label: 'Release Buy 5, line cancelled',
              },
            ],
          },
          proposal: null,
          inquiry_rows: [{ id: 'oir-3', verb: 'ORDER', qty: '5', state: 'raised' }],
          decision: 'confirm',
          applied_state: 'pending',
          board_link:
            '/project-sales/fulfilment-planning?orders=SO381895&cell=SRTWCX7405-RL-S-PJ|2026-09-10',
        },
      ],
    },
  ],
};
