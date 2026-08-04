/**
 * SCM S5 - Phase 1 fixture for Plan Exceptions.
 *
 * Phase 2 flips `USE_PLAN_EXCEPTION_MOCKS` to false and DELETES this file. Nothing
 * imports it except `planExceptionService` and its own tests.
 *
 * The fixture exists to make the SCREEN's states reachable by clicking, and one of those
 * states is the ordering rule itself. Three rows below carry IDENTICAL arithmetic - the
 * same surplus, the same quantity, the same dates - and differ only in the item's
 * reading, so the proposed actions come back in three different orders (AC-D10). A
 * fixture with one surplus row would let the whole inversion ship unlooked-at:
 *
 *   - `SRT367-GM`   discontinued, C/Z, retail -> KEEP the order and pool the stock first.
 *                   Never cancel or defer first: it is the last obtainable stock of a
 *                   product the supplier is closing out (AC-D11).
 *   - `C-FH24`      active, A/X, project      -> RELINK to another order first.
 *   - `ACC6002`     active, C/Z, retail       -> PUSH the ETA out first.
 *
 * The other rows cover the remaining types and the decided states:
 *
 *   - `SRTWB1514-FULL GLAZE`  shortfall_earlier - a site pulled in, so the gap is now
 *                             before the PO lands.
 *   - `SRTWC8613-RL`          supply_early, already APPROVED by a named person.
 *   - `SRTWT7408`             supply_wrong_location, already REJECTED with a reason.
 *
 * `delta_count` 412 against 6 exceptions is deliberate: the reduction is the value of the
 * screen (AC-D2b), and a fixture where every delta became an exception would misrepresent
 * what the batch normally looks like.
 */
import type {
  ItemReading,
  PlanException,
  PlanExceptionDecisionInput,
  PlanExceptionDecisionResult,
  PlanExceptionReport,
  ProposedAction,
  TimelinePoint,
} from '../types/planException.types';

/** Flip to false in Phase 2. The real branch in the service is already written. */
export const USE_PLAN_EXCEPTION_MOCKS = true;

/** How long the mock takes to "fetch", so the loading skeleton is actually visible. */
const MOCK_LATENCY_MS = 400;

const AS_OF = '2026-08-04';
const RUN_ID = 'run-2026-w32';

function reading(
  lifecycle: string,
  velocity: string,
  business: string,
  lastPo: string | null,
): ItemReading {
  return {
    lifecycle: { value: lifecycle, source: 'products.is_discontinued' },
    velocity: { value: velocity, source: 'scm.item_classification' },
    business: { value: business, source: 'market_segments.demand_class' },
    last_po: { value: lastPo, source: 'purchase_orders.order_date' },
  };
}

function points(
  rows: Array<[string, number, string | null]>,
): TimelinePoint[] {
  return rows.map(([date, net, label]) => ({ date, net, label }));
}

function action(
  code: ProposedAction['code'],
  rank: number,
  rationale: string,
  extra: Partial<ProposedAction> = {},
): ProposedAction {
  return {
    code,
    rank,
    rationale,
    candidate_so_number: null,
    candidate_need_by: null,
    candidate_warehouse_code: null,
    ...extra,
  };
}

const ROWS: PlanException[] = [
  {
    exception_id: 'exc-1',
    exception_type: 'supply_surplus',
    product_code: 'SRT367-GM',
    product_name: 'Sorento 367 Gunmetal',
    uom: 'PCS',
    warehouse_code: 'MWH-S/L',
    pool_code: 'MWH-S/L',
    po_number: 'PO26-0411',
    po_expected_date: '2026-09-18',
    quantity: 240,
    timeline: {
      before_points: points([
        ['2026-08-04', 60, null],
        ['2026-09-18', 300, 'PO26-0411 arrives'],
        ['2026-09-30', 60, 'SO26-0904 due'],
      ]),
      after_points: points([
        ['2026-08-04', 60, null],
        ['2026-09-18', 300, 'PO26-0411 arrives'],
        ['2026-09-30', 300, 'SO26-0904 cancelled'],
      ]),
      before_shortfall_at: null,
      after_shortfall_at: null,
      before_shortfall_qty: null,
      after_shortfall_qty: null,
    },
    reading: reading('Discontinued', 'C / Z', 'Retail', '2026-03-02'),
    actions: [
      action(
        'keep_and_pool',
        1,
        'Discontinued, so this is the last stock obtainable. Cancelling or deferring risks the supplier closing the line.',
        { candidate_warehouse_code: 'BRW-AM' },
      ),
      action('relink_so', 2, 'A slow-moving retail item has no waiting order to move it to today.'),
      action('push_eta', 3, 'Only after the line is confirmed still open.'),
      action('accept', 4, 'Take the surplus knowingly.'),
    ],
    status: 'open',
    decided_by: null,
    decided_at: null,
    decided_action: null,
    decision_reason: null,
  },
  {
    exception_id: 'exc-2',
    exception_type: 'supply_surplus',
    product_code: 'C-FH24',
    product_name: 'Ceramic FH24',
    uom: 'PCS',
    warehouse_code: 'WH3-AM',
    pool_code: 'WH3-AM',
    po_number: 'PO26-0398',
    po_expected_date: '2026-09-12',
    quantity: 240,
    timeline: {
      before_points: points([
        ['2026-08-04', 120, null],
        ['2026-09-12', 360, 'PO26-0398 arrives'],
        ['2026-09-25', 120, 'SO26-0877 due'],
      ]),
      after_points: points([
        ['2026-08-04', 120, null],
        ['2026-09-12', 360, 'PO26-0398 arrives'],
        ['2026-09-25', 360, 'SO26-0877 deferred to 2027'],
      ]),
      before_shortfall_at: null,
      after_shortfall_at: null,
      before_shortfall_qty: null,
      after_shortfall_qty: null,
    },
    reading: reading('Active', 'A / X', 'Project', '2026-06-19'),
    actions: [
      action(
        'relink_so',
        1,
        'Fast-moving project item with another order already waiting on the same stock.',
        { candidate_so_number: 'SO26-0931', candidate_need_by: '2026-09-30' },
      ),
      action('change_location', 2, 'Move it to where the waiting order ships from.', {
        candidate_warehouse_code: 'MWH-RSV',
      }),
      action('split', 3, 'Move only the part the other order needs.'),
      action('push_eta', 4, 'Last resort on an A/X item: the stock turns anyway.'),
    ],
    status: 'open',
    decided_by: null,
    decided_at: null,
    decided_action: null,
    decision_reason: null,
  },
  {
    exception_id: 'exc-3',
    exception_type: 'supply_surplus',
    product_code: 'ACC6002',
    product_name: 'Accessory 6002',
    uom: 'PCS',
    warehouse_code: 'MWH-RSV',
    pool_code: 'MWH-S/L',
    po_number: 'PO26-0402',
    po_expected_date: '2026-09-15',
    quantity: 240,
    timeline: {
      before_points: points([
        ['2026-08-04', 40, null],
        ['2026-09-15', 280, 'PO26-0402 arrives'],
        ['2026-09-28', 40, 'SO26-0888 due'],
      ]),
      after_points: points([
        ['2026-08-04', 40, null],
        ['2026-09-15', 280, 'PO26-0402 arrives'],
        ['2026-09-28', 280, 'SO26-0888 cancelled'],
      ]),
      before_shortfall_at: null,
      after_shortfall_at: null,
      before_shortfall_qty: null,
      after_shortfall_qty: null,
    },
    reading: reading('Active', 'C / Z', 'Retail', '2026-05-08'),
    actions: [
      action(
        'push_eta',
        1,
        'Still made to order, and slow-moving: later arrival costs nothing and frees the cash.',
      ),
      action('release_to_pool', 2, 'Let any location draw on it instead.', {
        candidate_warehouse_code: 'BRW-AM',
      }),
      action('split', 3, 'Take part now if a smaller quantity is genuinely wanted.'),
      action('accept', 4, 'Take the surplus knowingly.'),
    ],
    status: 'open',
    decided_by: null,
    decided_at: null,
    decided_action: null,
    decision_reason: null,
  },
  {
    exception_id: 'exc-4',
    exception_type: 'shortfall_earlier',
    product_code: 'SRTWB1514-FULL GLAZE',
    product_name: 'Sorento WB1514 Full Glaze',
    uom: 'PCS',
    warehouse_code: 'MWH-S/L',
    pool_code: 'MWH-S/L',
    po_number: 'PO26-0377',
    po_expected_date: '2026-10-06',
    quantity: 180,
    timeline: {
      before_points: points([
        ['2026-08-04', 210, null],
        ['2026-10-06', 390, 'PO26-0377 arrives'],
        ['2026-10-20', 30, 'SO26-0850 due'],
      ]),
      after_points: points([
        ['2026-08-04', 210, null],
        ['2026-09-08', 30, 'SO26-0850 pulled in'],
        ['2026-09-22', -150, 'SO26-0902 due'],
        ['2026-10-06', 30, 'PO26-0377 arrives'],
      ]),
      before_shortfall_at: null,
      after_shortfall_at: '2026-09-22',
      before_shortfall_qty: null,
      after_shortfall_qty: 150,
    },
    reading: reading('Active', 'A / Y', 'Project', '2026-04-27'),
    actions: [
      action('relink_so', 1, 'Another location holds uncommitted stock that lands before the new date.', {
        candidate_so_number: 'SO26-0902',
        candidate_need_by: '2026-09-22',
        candidate_warehouse_code: 'WH3-AM',
      }),
      action('change_location', 2, 'Divert the placed order to where it is now needed.', {
        candidate_warehouse_code: 'MWH-S/L',
      }),
      action('accept', 3, 'Accept a late delivery on this order.'),
    ],
    status: 'open',
    decided_by: null,
    decided_at: null,
    decided_action: null,
    decision_reason: null,
  },
  {
    exception_id: 'exc-5',
    exception_type: 'supply_early',
    product_code: 'SRTWC8613-RL',
    product_name: 'Sorento WC8613 RL',
    uom: 'PCS',
    warehouse_code: 'WH3-AM',
    pool_code: 'WH3-AM',
    po_number: 'PO26-0365',
    po_expected_date: '2026-08-29',
    quantity: 96,
    timeline: {
      before_points: points([
        ['2026-08-04', 12, null],
        ['2026-08-29', 108, 'PO26-0365 arrives'],
        ['2026-09-05', 12, 'SO26-0810 due'],
      ]),
      after_points: points([
        ['2026-08-04', 12, null],
        ['2026-08-29', 108, 'PO26-0365 arrives'],
        ['2026-11-14', 12, 'SO26-0810 moved out'],
      ]),
      before_shortfall_at: null,
      after_shortfall_at: null,
      before_shortfall_qty: null,
      after_shortfall_qty: null,
    },
    reading: reading('Active', 'B / X', 'Project', '2026-05-30'),
    actions: [
      action('push_eta', 1, 'Eleven weeks of holding cost avoided on stock nothing needs yet.'),
      action('release_to_pool', 2, 'Let another location draw on it in the meantime.'),
      action('accept', 3, 'Hold it early.'),
    ],
    status: 'approved',
    decided_by: 'Joey Tan',
    decided_at: '2026-08-04T18:12:00',
    decided_action: 'push_eta',
    decision_reason: 'Supplier confirmed a November slot.',
  },
  {
    exception_id: 'exc-6',
    exception_type: 'supply_wrong_location',
    product_code: 'SRTWT7408',
    product_name: 'Sorento WT7408',
    uom: 'PCS',
    warehouse_code: 'MWH-RSV',
    pool_code: 'MWH-S/L',
    po_number: 'PO26-0389',
    po_expected_date: '2026-09-03',
    quantity: 60,
    timeline: {
      before_points: points([
        ['2026-08-04', 0, null],
        ['2026-09-03', 60, 'PO26-0389 arrives MWH-RSV'],
      ]),
      after_points: points([
        ['2026-08-04', 0, null],
        ['2026-09-03', 60, 'PO26-0389 arrives MWH-RSV'],
        ['2026-09-10', -60, 'SO26-0899 ships from WH3-AM'],
      ]),
      before_shortfall_at: null,
      after_shortfall_at: '2026-09-10',
      before_shortfall_qty: null,
      after_shortfall_qty: 60,
    },
    reading: reading('Active', 'B / Y', 'Dealer', '2026-07-11'),
    actions: [
      action('change_location', 1, 'The order that needs it ships from a different warehouse.', {
        candidate_warehouse_code: 'WH3-AM',
      }),
      action('release_to_pool', 2, 'Release it so any location in the pool may draw on it.'),
      action('accept', 3, 'Move the stock internally after it lands.'),
    ],
    status: 'rejected',
    decided_by: 'Joey Tan',
    decided_at: '2026-08-04T18:20:00',
    decided_action: null,
    decision_reason: 'Ms Tee is consolidating this container at MWH-RSV anyway.',
  },
];

/** Mutable copy so decisions persist across a session, like the real endpoint would. */
let rows: PlanException[] = ROWS.map((r) => ({ ...r }));

function counts(current: PlanException[]) {
  return {
    delta_count: 412,
    exception_count: current.length,
    open_count: current.filter((r) => r.status === 'open').length,
    approved_count: current.filter((r) => r.status === 'approved').length,
    rejected_count: current.filter((r) => r.status === 'rejected').length,
  };
}

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), MOCK_LATENCY_MS));
}

export function mockPlanExceptionReport(): Promise<PlanExceptionReport> {
  return delay({
    run_id: RUN_ID,
    as_of: AS_OF,
    generated_at: '2026-08-04T17:58:00',
    last_upload_at: '2026-08-04T17:55:00',
    counts: counts(rows),
    rows: rows.map((r) => ({ ...r })),
  });
}

export function mockDecideException(
  input: PlanExceptionDecisionInput,
): Promise<PlanExceptionDecisionResult> {
  const decidedAt = '2026-08-04T19:04:00';
  rows = rows.map((r) =>
    r.exception_id === input.exception_id
      ? {
          ...r,
          status: input.status,
          decided_by: 'Joey Tan',
          decided_at: decidedAt,
          decided_action: input.status === 'approved' ? input.action_code : null,
          decision_reason: input.reason,
        }
      : r,
  );
  return delay({
    exception_id: input.exception_id,
    status: input.status,
    decided_by: 'Joey Tan',
    decided_at: decidedAt,
    decided_action: input.status === 'approved' ? input.action_code : null,
    decision_reason: input.reason,
  });
}

/** Test-only: put the fixture back so decisions in one test do not leak into the next. */
export function resetPlanExceptionMocks(): void {
  rows = ROWS.map((r) => ({ ...r }));
}
