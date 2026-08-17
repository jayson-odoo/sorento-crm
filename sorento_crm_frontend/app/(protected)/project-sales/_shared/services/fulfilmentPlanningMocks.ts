/**
 * Phase 1 fixtures for Fulfilment Planning, served only when
 * `NEXT_PUBLIC_PROJECT_SO_MOCK=1` (Stage 1C, slice note section 7). DELETED when Phase 2
 * lands: the component tests carry their own fixtures, and a second source of these shapes
 * drifts from the real one.
 *
 * They live beside the service rather than inside it so the service reads as the contract
 * it is. One Project SO per composition case, so every branch of the sheet is reachable by
 * clicking a row rather than by editing code:
 *
 *   PSO-000123  reserve + buy with reasons, the hot-selling BRW cap, timely and advisory
 *               incoming, an unavailable retail classification, a discontinued buy, and
 *               borrow candidates at another location and on another project
 *   PSO-000124  a line the engine could not compose to its open quantity
 *   PSO-000125  balanced on screen, refused by the server with failing lines
 *   PSO-000126  already confirmed: the frozen view
 *   PSO-000127  confirmed, then challenged by a fact that moved underneath it
 *
 * Same golden order book as the sales-order fixtures (Tuju Residences, PO HQ/26/01/121),
 * so the two screens describe one business rather than two invented ones. Warehouse and
 * project ids are UUID-shaped to prove the screen never prints one.
 */
import type {
  ConfirmResult,
  ConfirmSupplyBody,
  FulfilmentPlanningRow,
  ReconciliationSummary,
  SupplyLine,
  SupplyProposal,
} from '../types/fulfilmentPlanning.types';
import type { OrderInquiryRow } from '../types/orderInquiry.types';
import { ConfirmSupplyError } from './fulfilmentPlanningService';

const WH = {
  brw: 'a1000000-0000-4000-8000-000000000001',
  hq: 'a1000000-0000-4000-8000-000000000002',
  dealer: 'a1000000-0000-4000-8000-000000000003',
  jb: 'a1000000-0000-4000-8000-000000000004',
};

const DONOR_PROJECT_ID = 'b2000000-0000-4000-8000-000000000001';

const CLEAN = 'mock-pso-supply-clean';
const UNBALANCED = 'mock-pso-supply-unbalanced';
const REFUSED = 'mock-pso-supply-refused';
const CONFIRMED = 'mock-pso-supply-confirmed';
const CHALLENGED = 'mock-pso-supply-challenged';

/**
 * A confirmation that landed in this browser session. It is what makes the golden path
 * demonstrable end to end: confirm, and the same order comes back Confirmed with the
 * composition frozen, exactly as a reload from the server would.
 */
const CONFIRMED_IN_SESSION = new Map<
  string,
  { revision_no: number; confirmed_at: string; body: ConfirmSupplyBody }
>();

interface MockOrder {
  id: string;
  provisional_ref: string;
  autocount_doc_no: string | null;
  core_so_number: string | null;
  project_id: string;
  project_code: string;
  project_name: string;
  customer_name: string;
  po_number: string;
  area_group: string | null;
  status: string;
  updated_at: string;
  lines: SupplyLine[];
  decision?: SupplyProposal['decision'];
}

// --------------------------------------------------------------------- lines

const CLEAN_LINES: SupplyLine[] = [
  {
    // Reserve + timely incoming + Buy, each with the reason its rule wrote (AC-B14), and
    // both kinds of borrow candidate beside them.
    project_line_id: 'clean-l1',
    line_no: 1,
    item_code: 'CB6633',
    description: 'CABANA S/STEEL FLOOR GRATING 6"',
    uom: 'UNIT',
    open_qty: '600',
    required_date: '2026-09-01',
    fulfilment_location: 'BRW-BB',
    is_dealer_hot_selling: false,
    classification_unavailable: false,
    is_discontinued: false,
    pool_location: 'BRW-BB',
    pool_cap: null,
    pool_reorder_level: '120',
    components: [
      {
        kind: 'timely_spo',
        qty: '100',
        reason: 'SPO-2026-0311 arrives at BRW-BB on 01 Sep 2026, on the required date.',
        source_location: 'BRW-BB',
        source_warehouse_id: WH.brw,
      },
      {
        kind: 'reserve',
        qty: '200',
        reason: 'Free stock at BRW-BB covers the need by the required date.',
        source_location: 'BRW-BB',
        source_warehouse_id: WH.brw,
      },
      {
        kind: 'buy',
        qty: '300',
        reason: 'Remaining uncovered need.',
      },
    ],
    timely_spo: [{ spo_number: 'SPO-2026-0311', arrival_date: '2026-09-01', qty: '100' }],
    advisory_spo: [{ spo_number: 'SPO-2026-0402', arrival_date: '2026-10-14', qty: '250' }],
    borrow_candidates: [
      {
        source: 'other_location',
        warehouse_code: 'HQ',
        warehouse_id: WH.hq,
        free_qty: '80',
        donor_impact: {
          free_before: '80',
          free_after_full_borrow: '0',
          committed_qty: '140',
        },
      },
      {
        source: 'other_project',
        warehouse_code: 'JB',
        warehouse_id: WH.jb,
        donor_project_ref: 'PRJ-0052 Seri Emas Phase 2',
        donor_project_id: DONOR_PROJECT_ID,
        free_qty: '50',
        donor_impact: {
          free_before: '50',
          free_after_full_borrow: '0',
          committed_qty: '50',
        },
      },
    ],
  },
  {
    // The plan's own worked example (AC-B08): hot-selling, so dealer free stock is out and
    // the pool draw stops at its reorder level.
    project_line_id: 'clean-l2',
    line_no: 2,
    item_code: 'SRT501-CP',
    description: 'SORENTO BASIN MIXER 501 CHROME',
    uom: 'UNIT',
    open_qty: '70',
    required_date: '2026-09-01',
    fulfilment_location: 'BRW-BB',
    is_dealer_hot_selling: true,
    classification_unavailable: false,
    is_discontinued: false,
    pool_location: 'BRW-BB',
    pool_cap: '40',
    pool_reorder_level: '80',
    components: [
      {
        kind: 'reserve',
        qty: '40',
        reason: 'Free stock at BRW-BB above its reorder level of 80 covers 40 of the need.',
        source_location: 'BRW-BB',
        source_warehouse_id: WH.brw,
      },
      {
        kind: 'buy',
        qty: '30',
        reason: 'Remaining uncovered need.',
      },
    ],
    timely_spo: [],
    advisory_spo: [],
    borrow_candidates: [
      {
        source: 'other_location',
        warehouse_code: 'HQ-DEALER',
        warehouse_id: WH.dealer,
        free_qty: '50',
        donor_impact: {
          free_before: '50',
          free_after_full_borrow: '0',
          committed_qty: '0',
        },
      },
    ],
  },
  {
    // Nothing to reserve, nothing incoming, nobody to borrow from, and no classification
    // at any dealer warehouse. Four empty states on one card (AC-G02).
    project_line_id: 'clean-l3',
    line_no: 3,
    item_code: 'CB2201',
    description: 'CABANA FLOOR TRAP 4"',
    uom: 'UNIT',
    open_qty: '200',
    required_date: '2026-09-20',
    fulfilment_location: 'HQ',
    is_dealer_hot_selling: false,
    classification_unavailable: true,
    is_discontinued: false,
    pool_location: 'BRW-BB',
    pool_cap: null,
    pool_reorder_level: null,
    components: [
      {
        kind: 'buy',
        qty: '200',
        reason: 'Remaining uncovered need: no free stock at HQ or BRW-BB.',
      },
    ],
    timely_spo: [],
    advisory_spo: [],
    borrow_candidates: [],
  },
  {
    // Discontinued, and bought anyway because the customer is already committed - with a
    // warning and a reason nobody can skip (AC-B11).
    project_line_id: 'clean-l4',
    line_no: 4,
    item_code: 'SRT770-BK',
    description: 'SORENTO SHOWER SET 770 BLACK',
    uom: 'SET',
    open_qty: '25',
    required_date: '2026-09-25',
    fulfilment_location: 'HQ',
    is_dealer_hot_selling: false,
    classification_unavailable: false,
    is_discontinued: true,
    pool_location: 'BRW-BB',
    pool_cap: null,
    pool_reorder_level: '10',
    components: [
      {
        kind: 'buy',
        qty: '25',
        reason: 'Remaining uncovered need.',
      },
    ],
    timely_spo: [],
    advisory_spo: [{ spo_number: 'SPO-2026-0455', arrival_date: '2026-11-02', qty: '25' }],
    borrow_candidates: [],
  },
];

const UNBALANCED_LINES: SupplyLine[] = [
  {
    project_line_id: 'unbal-l1',
    line_no: 1,
    item_code: 'CB6633',
    description: 'CABANA S/STEEL FLOOR GRATING 6"',
    uom: 'UNIT',
    open_qty: '120',
    required_date: '2026-09-05',
    fulfilment_location: 'BRW-BB',
    is_dealer_hot_selling: false,
    classification_unavailable: false,
    is_discontinued: false,
    pool_location: 'BRW-BB',
    pool_cap: null,
    pool_reorder_level: '120',
    components: [
      {
        kind: 'reserve',
        qty: '20',
        reason: 'Free stock at BRW-BB covers the need by the required date.',
        source_location: 'BRW-BB',
        source_warehouse_id: WH.brw,
      },
      {
        kind: 'buy',
        qty: '80',
        reason: 'Remaining uncovered need.',
      },
    ],
    timely_spo: [],
    advisory_spo: [],
    borrow_candidates: [
      {
        source: 'other_location',
        warehouse_code: 'HQ',
        warehouse_id: WH.hq,
        free_qty: '60',
        donor_impact: {
          free_before: '60',
          free_after_full_borrow: '0',
          committed_qty: '20',
        },
      },
    ],
  },
];

const REFUSED_LINES: SupplyLine[] = [
  {
    project_line_id: 'refused-l1',
    line_no: 1,
    item_code: 'SRT382-6',
    description: 'SORENTO S/S SINK MIXER 382-6',
    uom: 'UNIT',
    open_qty: '40',
    required_date: '2026-09-08',
    fulfilment_location: 'BRW-BB',
    is_dealer_hot_selling: false,
    classification_unavailable: false,
    is_discontinued: false,
    pool_location: 'BRW-BB',
    pool_cap: null,
    pool_reorder_level: '30',
    components: [
      {
        kind: 'reserve',
        qty: '40',
        reason: 'Free stock at BRW-BB covers the need by the required date.',
        source_location: 'BRW-BB',
        source_warehouse_id: WH.brw,
      },
    ],
    timely_spo: [],
    advisory_spo: [],
    borrow_candidates: [],
  },
  {
    project_line_id: 'refused-l2',
    line_no: 2,
    item_code: 'CB2201',
    description: 'CABANA FLOOR TRAP 4"',
    uom: 'UNIT',
    open_qty: '60',
    required_date: '2026-09-08',
    fulfilment_location: 'BRW-BB',
    is_dealer_hot_selling: false,
    classification_unavailable: false,
    is_discontinued: false,
    pool_location: 'BRW-BB',
    pool_cap: null,
    pool_reorder_level: null,
    components: [{ kind: 'buy', qty: '60', reason: 'Remaining uncovered need.' }],
    timely_spo: [],
    advisory_spo: [],
    borrow_candidates: [],
  },
];

const CONFIRMED_LINES: SupplyLine[] = [
  {
    project_line_id: 'confirmed-l1',
    line_no: 1,
    item_code: 'CB6633',
    description: 'CABANA S/STEEL FLOOR GRATING 6"',
    uom: 'UNIT',
    open_qty: '300',
    required_date: '2026-08-28',
    fulfilment_location: 'BRW-BB',
    is_dealer_hot_selling: false,
    classification_unavailable: false,
    is_discontinued: false,
    pool_location: 'BRW-BB',
    pool_cap: null,
    pool_reorder_level: '120',
    components: [],
    timely_spo: [{ spo_number: 'SPO-2026-0288', arrival_date: '2026-08-20', qty: '50' }],
    advisory_spo: [],
    borrow_candidates: [],
    frozen: {
      open_qty: '300',
      components: [
        {
          kind: 'timely_spo',
          qty: '50',
          reason: 'SPO-2026-0288 arrives at BRW-BB on 20 Aug 2026, before the required date.',
          source_location: 'BRW-BB',
          source_warehouse_id: WH.brw,
        },
        {
          kind: 'reserve',
          qty: '150',
          reason: 'Free stock at BRW-BB covers the need by the required date.',
          source_location: 'BRW-BB',
          source_warehouse_id: WH.brw,
        },
        {
          kind: 'borrow',
          qty: '40',
          reason: 'Free stock at HQ, outside the reserve pool for this location.',
          source_location: 'HQ',
          source_warehouse_id: WH.hq,
          cs_reason: 'HQ has no delivery booked before October.',
        },
        { kind: 'buy', qty: '60', reason: 'Remaining uncovered need.' },
      ],
    },
  },
  {
    project_line_id: 'confirmed-l2',
    line_no: 2,
    item_code: 'SRT770-BK',
    description: 'SORENTO SHOWER SET 770 BLACK',
    uom: 'SET',
    open_qty: '10',
    required_date: '2026-08-30',
    fulfilment_location: 'HQ',
    is_dealer_hot_selling: false,
    classification_unavailable: false,
    is_discontinued: true,
    pool_location: 'BRW-BB',
    pool_cap: null,
    pool_reorder_level: null,
    components: [],
    timely_spo: [],
    advisory_spo: [],
    borrow_candidates: [],
    frozen: {
      open_qty: '10',
      components: [
        {
          kind: 'buy',
          qty: '10',
          reason: 'Remaining uncovered need.',
          cs_reason: 'Customer accepted the last production batch in writing.',
        },
      ],
    },
  },
];

const CHALLENGED_LINES: SupplyLine[] = [
  {
    project_line_id: 'challenged-l1',
    line_no: 1,
    item_code: 'SRT382-6',
    description: 'SORENTO S/S SINK MIXER 382-6',
    uom: 'UNIT',
    open_qty: '150',
    required_date: '2026-09-12',
    fulfilment_location: 'BRW-BB',
    is_dealer_hot_selling: false,
    classification_unavailable: false,
    is_discontinued: false,
    pool_location: 'BRW-BB',
    pool_cap: null,
    pool_reorder_level: '60',
    components: [
      {
        kind: 'reserve',
        qty: '90',
        reason: 'Free stock at BRW-BB covers the need by the required date.',
        source_location: 'BRW-BB',
        source_warehouse_id: WH.brw,
      },
      { kind: 'buy', qty: '60', reason: 'Remaining uncovered need.' },
    ],
    timely_spo: [],
    advisory_spo: [],
    borrow_candidates: [
      {
        source: 'other_location',
        warehouse_code: 'HQ',
        warehouse_id: WH.hq,
        free_qty: '30',
        donor_impact: {
          free_before: '30',
          free_after_full_borrow: '0',
          committed_qty: '10',
        },
      },
    ],
  },
];

// -------------------------------------------------------------------- orders

const MOCK_ORDERS: MockOrder[] = [
  {
    id: CLEAN,
    provisional_ref: 'PSO-000123',
    autocount_doc_no: 'SO376201',
    core_so_number: 'SO376201',
    project_id: 'mock-project-tuju',
    project_code: 'PRJ-0041',
    project_name: 'Tuju Residences',
    customer_name: 'Buimaco Sdn Bhd (Project)',
    po_number: 'HQ/26/01/121',
    area_group: 'TOWER',
    status: 'published',
    updated_at: '2026-08-14T02:41:00',
    lines: CLEAN_LINES,
  },
  {
    id: UNBALANCED,
    provisional_ref: 'PSO-000124',
    autocount_doc_no: 'SO376202',
    core_so_number: 'SO376202',
    project_id: 'mock-project-tuju',
    project_code: 'PRJ-0041',
    project_name: 'Tuju Residences',
    customer_name: 'Buimaco Sdn Bhd (Project)',
    po_number: 'HQ/26/01/121',
    area_group: 'COMMON AREA',
    status: 'published',
    updated_at: '2026-08-15T07:12:00',
    lines: UNBALANCED_LINES,
  },
  {
    id: REFUSED,
    provisional_ref: 'PSO-000125',
    autocount_doc_no: 'SO376203',
    core_so_number: 'SO376203',
    project_id: 'mock-project-seri',
    project_code: 'PRJ-0052',
    project_name: 'Seri Emas Phase 2',
    customer_name: 'Hong Bee Hardware Sdn Bhd',
    po_number: 'HB/26/03/008',
    area_group: 'BLOCK B',
    status: 'published',
    updated_at: '2026-08-16T01:05:00',
    lines: REFUSED_LINES,
  },
  {
    id: CONFIRMED,
    provisional_ref: 'PSO-000126',
    autocount_doc_no: 'SO376204',
    core_so_number: 'SO376204',
    project_id: 'mock-project-tuju',
    project_code: 'PRJ-0041',
    project_name: 'Tuju Residences',
    customer_name: 'Buimaco Sdn Bhd (Project)',
    po_number: 'HQ/26/01/121',
    area_group: 'BLOCK A',
    status: 'published',
    updated_at: '2026-08-16T09:30:00',
    lines: CONFIRMED_LINES,
    decision: {
      revision_no: 2,
      state: 'active',
      confirmed_by_name: 'Nurul Aina',
      confirmed_at: '2026-08-16T09:30:00',
    },
  },
  {
    id: CHALLENGED,
    provisional_ref: 'PSO-000127',
    autocount_doc_no: 'SO376205',
    core_so_number: 'SO376205',
    project_id: 'mock-project-seri',
    project_code: 'PRJ-0052',
    project_name: 'Seri Emas Phase 2',
    customer_name: 'Hong Bee Hardware Sdn Bhd',
    po_number: 'HB/26/03/008',
    area_group: 'BLOCK C',
    status: 'amended',
    updated_at: '2026-08-17T02:20:00',
    lines: CHALLENGED_LINES,
    decision: {
      revision_no: 1,
      state: 'challenged',
      confirmed_by_name: 'Nurul Aina',
      confirmed_at: '2026-08-15T04:10:00',
      challenged_reason:
        'Line 1 was amended from 120 to 150 after this revision was confirmed.',
    },
  },
];

function orderOf(psoId: string): MockOrder {
  return MOCK_ORDERS.find((order) => order.id === psoId) ?? MOCK_ORDERS[0];
}

function reviewStateOf(order: MockOrder): FulfilmentPlanningRow['review_state'] {
  if (CONFIRMED_IN_SESSION.has(order.id)) return 'confirmed';
  return order.decision?.state === 'active' ? 'confirmed' : 'needs_cs_review';
}

/** The worklist rows. A function, not a constant: a confirmation flips one of them. */
export function MOCK_PLANNING_ROWS(): FulfilmentPlanningRow[] {
  return MOCK_ORDERS.map((order) => ({
    id: order.id,
    provisional_ref: order.provisional_ref,
    autocount_doc_no: order.autocount_doc_no,
    project_id: order.project_id,
    project_code: order.project_code,
    project_name: order.project_name,
    customer_name: order.customer_name,
    po_number: order.po_number,
    area_group: order.area_group,
    status: order.status,
    line_count: order.lines.length,
    lines_linked: order.lines.length,
    exception_count: 0,
    review_state: reviewStateOf(order),
    updated_at: order.updated_at,
  }));
}

/**
 * Stage 1B's card, derived from the same lines rather than written twice: every fixture
 * order here is past reconciliation, which is what makes it a supply case at all.
 */
export function mockReconciliation(psoId: string): ReconciliationSummary {
  const order = orderOf(psoId);
  return {
    project_sales_order_id: order.id,
    provisional_ref: order.provisional_ref,
    autocount_doc_no: order.autocount_doc_no,
    project_id: order.project_id,
    project_code: order.project_code,
    project_name: order.project_name,
    customer_name: order.customer_name,
    po_number: order.po_number,
    area_group: order.area_group,
    status: order.status,
    review_state: reviewStateOf(order),
    header: {
      outcome: 'linked',
      core_so_number: order.core_so_number,
      reason: `Linked to sales order ${order.core_so_number}.`,
    },
    lines: order.lines.map((line) => ({
      id: line.project_line_id,
      line_no: line.line_no,
      product_code: line.item_code,
      description: line.description,
      qty: line.open_qty,
      uom: line.uom,
      delivery_date: line.required_date,
      stock_location: line.fulfilment_location,
      link: 'linked' as const,
      candidate_count: 1,
      reason: 'Matched on product and required date.',
    })),
    exceptions: [],
    lines_total: order.lines.length,
    lines_linked: order.lines.length,
  };
}

/** The composition, including what a confirmation done in this session froze. */
export function mockSupply(psoId: string): SupplyProposal {
  const order = orderOf(psoId);
  const session = CONFIRMED_IN_SESSION.get(order.id);

  const lines: SupplyLine[] = session
    ? order.lines.map((line) => {
        const submitted = session.body.lines.find(
          (candidate) => candidate.project_line_id === line.project_line_id,
        );
        if (!submitted) return line;
        return {
          ...line,
          frozen: {
            open_qty: line.open_qty,
            components: [
              ...(Number(submitted.timely_spo_qty) > 0
                ? [
                    {
                      kind: 'timely_spo' as const,
                      qty: submitted.timely_spo_qty,
                      reason:
                        line.components.find((component) => component.kind === 'timely_spo')
                          ?.reason ?? 'Incoming that arrives by the required date.',
                      source_location: line.fulfilment_location,
                    },
                  ]
                : []),
              ...submitted.reserve.map((row) => ({
                kind: 'reserve' as const,
                qty: row.qty,
                reason:
                  line.components.find((component) => component.kind === 'reserve')?.reason ??
                  'Free stock covers the need by the required date.',
                source_location:
                  line.components.find(
                    (component) => component.source_warehouse_id === row.warehouse_id,
                  )?.source_location ?? line.fulfilment_location,
              })),
              ...submitted.borrow.map((row) => {
                const candidate = line.borrow_candidates.find(
                  (entry) => entry.warehouse_id === row.warehouse_id,
                );
                return {
                  kind: 'borrow' as const,
                  qty: row.qty,
                  reason:
                    row.source === 'other_project'
                      ? `Held by ${candidate?.donor_project_ref ?? 'another project'}.`
                      : `Free stock at ${candidate?.warehouse_code ?? 'another location'}, outside the reserve pool for this location.`,
                  source_location: candidate?.warehouse_code,
                  donor_project_ref: candidate?.donor_project_ref,
                  cs_reason: row.reason,
                };
              }),
              ...(Number(submitted.buy_qty) > 0
                ? [
                    {
                      kind: 'buy' as const,
                      qty: submitted.buy_qty,
                      reason:
                        line.components.find((component) => component.kind === 'buy')?.reason ??
                        'Remaining uncovered need.',
                      cs_reason: submitted.buy_reason ?? null,
                    },
                  ]
                : []),
            ],
          },
        };
      })
    : order.lines;

  return {
    project_sales_order_id: order.id,
    provisional_ref: order.provisional_ref,
    autocount_doc_no: order.autocount_doc_no,
    project_id: order.project_id,
    project_code: order.project_code,
    project_name: order.project_name,
    status: order.status,
    review_state: reviewStateOf(order),
    decision: session
      ? {
          revision_no: session.revision_no,
          state: 'active',
          confirmed_by_name: 'You',
          confirmed_at: session.confirmed_at,
        }
      : order.decision,
    lines,
  };
}

/**
 * PSO-000125 always refuses, naming the lines that refused it, and writes nothing. Every
 * other fixture order commits and comes back Confirmed.
 */
export function mockConfirmSupply(
  psoId: string,
  body: ConfirmSupplyBody,
): ConfirmResult {
  const order = orderOf(psoId);
  if (order.id === REFUSED) {
    throw new ConfirmSupplyError('This sales order could not be confirmed', [
      {
        line_no: 1,
        item_code: 'SRT382-6',
        reason: 'Only 25 of the 40 reserved units are still free at BRW-BB.',
      },
      {
        line_no: 2,
        item_code: 'CB2201',
        reason: 'The open quantity changed to 80 after this sheet was opened.',
      },
    ]);
  }
  const revision = (order.decision?.revision_no ?? 0) + 1;
  const confirmedAt = new Date().toISOString();
  CONFIRMED_IN_SESSION.set(order.id, { revision_no: revision, confirmed_at: confirmedAt, body });
  return {
    revision_no: revision,
    confirmed_at: confirmedAt,
    review_state: 'confirmed',
    inquiry_rows_created: body.lines.filter((line) => Number(line.buy_qty) > 0).length,
    exceptions: [],
  };
}

/**
 * The Buy-only handoff of the confirmed fixture order (PSO-000126), so Order Inquiry and
 * the sheet describe one decision. One row per line with a positive Buy, plus the row the
 * previous revision raised and this one cancelled, which is what "at most one active row
 * per decision line" looks like from the buyer's side (AC-D05).
 */
export function MOCK_ORDER_INQUIRY_ROWS(projectId: string): OrderInquiryRow[] {
  const order = orderOf(CONFIRMED);
  if (projectId !== order.project_id) return [];
  return [
    {
      id: 'mock-oi-1',
      order_inquiry_id: 'mock-oi',
      sales_order_ref: order.core_so_number,
      project_so_ref: order.provisional_ref,
      line_no: 1,
      decision_revision: 2,
      item_code: 'CB6633',
      qty: '60',
      delivery_date: '2026-08-28',
      stock_location: 'BRW-BB',
      verb: 'ORDER',
      covered_by: null,
      state: 'raised',
      created_at: order.updated_at,
    },
    {
      id: 'mock-oi-2',
      order_inquiry_id: 'mock-oi',
      sales_order_ref: order.core_so_number,
      project_so_ref: order.provisional_ref,
      line_no: 2,
      decision_revision: 2,
      item_code: 'SRT770-BK',
      qty: '10',
      delivery_date: '2026-08-30',
      stock_location: 'HQ',
      verb: 'ORDER',
      covered_by: null,
      state: 'raised',
      created_at: order.updated_at,
    },
    {
      id: 'mock-oi-3',
      order_inquiry_id: 'mock-oi',
      sales_order_ref: order.core_so_number,
      project_so_ref: order.provisional_ref,
      line_no: 1,
      decision_revision: 1,
      item_code: 'CB6633',
      qty: '90',
      delivery_date: '2026-08-28',
      stock_location: 'BRW-BB',
      verb: 'ORDER',
      note: 'Superseded by revision 2',
      covered_by: null,
      state: 'cancelled',
      created_at: '2026-08-15T04:10:00',
    },
  ];
}
