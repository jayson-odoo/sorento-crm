import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import { PROJECT_SO_MOCK } from './projectSalesOrderService';
import type {
  FulfilmentPlanningListEnvelope,
  FulfilmentPlanningListParams,
  FulfilmentPlanningRow,
  ReconciliationSummary,
} from '../types/fulfilmentPlanning.types';

/**
 * Fulfilment Planning: the AutoCount reconciliation of a published Project SO (Stage 1B).
 *
 * EXPECTED API CONTRACT (Phase 1 is built against this; Phase 2 must match it, and any
 * deviation updates `documentation/plans/scm/STAGE1B-scm-front-planning-reconciliation.md`
 * section 3 in the same change). All three routes hang off the existing
 * `/api/v1/project-sales` router, read with `projects.projects.view`, rerun with
 * `projects.projects.edit`.
 *
 *   GET  /project-sales/fulfilment-planning?page&limit&query&review_state&project_id
 *        -> { data: FulfilmentPlanningRow[], pagination: { total, page, limit } }
 *
 *   GET  /project-sales/sales-orders/{pso_id}/reconciliation -> ReconciliationSummary
 *   POST /project-sales/sales-orders/{pso_id}/reconcile      -> ReconciliationSummary
 *
 * An exception's `message` carries the REASON only. The screen prints the subject itself
 * from `line_no` and `item_code` ("Line 2, SRT501-CP"), so a message that repeats it reads
 * as the same fact twice.
 *
 * The POST is idempotent: it re-evaluates the mapping, writes the links it can prove and
 * clears the ones that went stale, then answers with the same body the GET would. Running
 * it twice on an unchanged order changes nothing and returns the same summary.
 *
 * `NEXT_PUBLIC_PROJECT_SO_MOCK=1` serves the fixtures at the bottom of this file instead of
 * calling any of it, which is how the four reconciliation outcomes (needs review, a missing
 * line beside a surplus core line, an ambiguous pair, no document uploaded) plus the empty
 * and failed list are reachable while the backend for the same contract is being written.
 * The switch is the one `projectSalesOrderService` already owns, so a session is either all
 * mock or all live.
 */

const BASE = '/api/v1/project-sales';

/**
 * The repo's standard `{data, pagination: {...}}`, with the flat `{data, total, ...}` read
 * as a fallback for the same reason `projectSalesOrderService` reads it: a backend that
 * shipped against the earlier wording should degrade to a full grid, not a blank one.
 */
function normaliseEnvelope(
  body: unknown,
  fallbackLimit: number,
): FulfilmentPlanningListEnvelope {
  const raw = (body ?? {}) as {
    data?: FulfilmentPlanningRow[];
    total?: number;
    page?: number;
    limit?: number;
    pagination?: { total?: number; page?: number; limit?: number };
  };
  const rows = Array.isArray(raw.data) ? raw.data : [];
  return {
    data: rows,
    total: raw.pagination?.total ?? raw.total ?? rows.length,
    page: raw.pagination?.page ?? raw.page ?? 1,
    limit: raw.pagination?.limit ?? raw.limit ?? fallbackLimit,
  };
}

/** Every published or amended Project SO across projects, one row each. */
export async function listFulfilmentPlanning(
  params: FulfilmentPlanningListParams = {},
): Promise<FulfilmentPlanningListEnvelope> {
  if (PROJECT_SO_MOCK) return mockList(params);
  const limit = params.limit ?? 25;
  const search = buildDataGridParams(
    {
      pageIndex: (params.page ?? 1) - 1,
      pageSize: limit,
      sorting: [],
      searchQuery: params.query ?? '',
    },
    { review_state: params.review_state, project_id: params.project_id },
  );
  const response = await apiFetch(`${BASE}/fulfilment-planning?${search.toString()}`);
  if (!response.ok)
    throw new Error(
      await extractApiError(response, 'Failed to load the fulfilment planning list'),
    );
  return normaliseEnvelope(await response.json(), limit);
}

/** What reconciliation currently makes of one order. A pure read: it writes nothing. */
export async function getReconciliation(psoId: string): Promise<ReconciliationSummary> {
  if (PROJECT_SO_MOCK) return mockSummary(psoId);
  const response = await apiFetch(`${BASE}/sales-orders/${psoId}/reconciliation`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the reconciliation'));
  return response.json();
}

/**
 * Re-run the mapping after CS has answered whatever was in the way (uploaded the AutoCount
 * document, answered a difference, or waited for the outstanding SO book to carry the
 * number). Idempotent, so the button is safe to press on an order that is already clean.
 */
export async function rerunReconciliation(psoId: string): Promise<ReconciliationSummary> {
  if (PROJECT_SO_MOCK) return mockSummary(psoId);
  const response = await apiFetch(`${BASE}/sales-orders/${psoId}/reconcile`, {
    method: 'POST',
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to re-run the reconciliation'));
  return response.json();
}

// ---------------------------------------------------------------------------
// Fixtures, served only when NEXT_PUBLIC_PROJECT_SO_MOCK=1.
//
// Same golden set the sales-order fixtures use (Tuju Residences, PO HQ/26/01/121), so the
// two screens describe one order book rather than two invented ones. Each row is one of
// the outcomes section 2 of the slice note defines, so every branch of the sheet is
// reachable by clicking a row rather than by editing code.
// ---------------------------------------------------------------------------

/** The order whose reconciliation request always fails, so the sheet's error state is reachable. */
const MOCK_UNAVAILABLE_ID = 'mock-pso-unavailable';

const MOCK_ROWS: FulfilmentPlanningRow[] = [
  {
    // Clean: header linked, every line linked, nothing surplus. The only row that has
    // earned Needs CS review.
    id: 'mock-pso-clean',
    provisional_ref: 'PSO-000123',
    autocount_doc_no: 'SO376201',
    project_id: 'mock-project-tuju',
    project_code: 'PRJ-0041',
    project_name: 'Tuju Residences',
    customer_name: 'Buimaco Sdn Bhd (Project)',
    po_number: 'HQ/26/01/121',
    area_group: 'TOWER',
    status: 'published',
    line_count: 4,
    lines_linked: 4,
    exception_count: 0,
    review_state: 'needs_cs_review',
    updated_at: '2026-08-14T02:41:00',
  },
  {
    // One Project line with no core line left to take, and one core line no Project line
    // claims. The two are separate exceptions on purpose: they are answered in different
    // places.
    id: 'mock-pso-missing',
    provisional_ref: 'PSO-000124',
    autocount_doc_no: 'SO376202',
    project_id: 'mock-project-tuju',
    project_code: 'PRJ-0041',
    project_name: 'Tuju Residences',
    customer_name: 'Buimaco Sdn Bhd (Project)',
    po_number: 'HQ/26/01/121',
    area_group: 'COMMON AREA',
    status: 'published',
    line_count: 3,
    lines_linked: 1,
    exception_count: 3,
    review_state: 'awaiting_reconciliation',
    updated_at: '2026-08-15T07:12:00',
  },
  {
    // Two Project lines, same product, same date, two core lines the same. Nothing is
    // written for either: a guess here links a customer's quantity to the wrong delivery.
    id: 'mock-pso-ambiguous',
    provisional_ref: 'PSO-000125',
    autocount_doc_no: 'SO376203',
    project_id: 'mock-project-seri',
    project_code: 'PRJ-0052',
    project_name: 'Seri Emas Phase 2',
    customer_name: 'Hong Bee Hardware Sdn Bhd',
    po_number: 'HB/26/03/008',
    area_group: null,
    status: 'amended',
    line_count: 3,
    lines_linked: 1,
    exception_count: 2,
    review_state: 'awaiting_reconciliation',
    updated_at: '2026-08-16T01:05:00',
  },
  {
    // Published, but nobody has uploaded the AutoCount document yet, so there is nothing
    // to reconcile against and the lines were never candidates.
    id: 'mock-pso-nodoc',
    provisional_ref: 'PSO-000126',
    autocount_doc_no: null,
    project_id: 'mock-project-seri',
    project_code: 'PRJ-0052',
    project_name: 'Seri Emas Phase 2',
    customer_name: 'Hong Bee Hardware Sdn Bhd',
    po_number: 'HB/26/03/008',
    area_group: 'BLOCK B',
    status: 'published',
    line_count: 2,
    lines_linked: 0,
    exception_count: 1,
    review_state: 'awaiting_reconciliation',
    updated_at: '2026-08-16T09:30:00',
  },
  {
    id: MOCK_UNAVAILABLE_ID,
    provisional_ref: 'PSO-000127',
    autocount_doc_no: 'SO376204',
    project_id: 'mock-project-seri',
    project_code: 'PRJ-0052',
    project_name: 'Seri Emas Phase 2',
    customer_name: 'Hong Bee Hardware Sdn Bhd',
    po_number: 'HB/26/03/008',
    area_group: 'BLOCK C',
    status: 'published',
    line_count: 2,
    lines_linked: 0,
    exception_count: 1,
    review_state: 'awaiting_reconciliation',
    updated_at: '2026-08-16T10:02:00',
  },
];

function mockList(params: FulfilmentPlanningListParams): FulfilmentPlanningListEnvelope {
  if (params.mock_case === 'error') {
    throw new Error('Failed to load the fulfilment planning list');
  }
  const limit = params.limit ?? 25;
  if (params.mock_case === 'empty') {
    return { data: [], total: 0, page: 1, limit };
  }
  const needle = (params.query ?? '').trim().toLowerCase();
  const rows = MOCK_ROWS.filter((row) => {
    if (params.review_state && row.review_state !== params.review_state) return false;
    if (!needle) return true;
    return [
      row.provisional_ref,
      row.autocount_doc_no,
      row.project_name,
      row.project_code,
      row.customer_name,
      row.po_number,
      row.area_group,
    ]
      .filter(Boolean)
      .some((field) => (field as string).toLowerCase().includes(needle));
  });
  return { data: rows, total: rows.length, page: 1, limit };
}

function summaryBase(row: FulfilmentPlanningRow) {
  return {
    project_sales_order_id: row.id,
    provisional_ref: row.provisional_ref,
    autocount_doc_no: row.autocount_doc_no,
    project_id: row.project_id,
    project_code: row.project_code,
    project_name: row.project_name,
    customer_name: row.customer_name,
    po_number: row.po_number,
    area_group: row.area_group,
    status: row.status,
    review_state: row.review_state,
  };
}

function mockSummary(psoId: string): ReconciliationSummary {
  if (psoId === MOCK_UNAVAILABLE_ID) {
    throw new Error('Failed to load the reconciliation');
  }
  const row = MOCK_ROWS.find((entry) => entry.id === psoId) ?? MOCK_ROWS[0];
  const base = summaryBase(row);

  if (row.id === 'mock-pso-nodoc') {
    return {
      ...base,
      header: {
        outcome: 'no_document',
        core_so_number: null,
        reason: 'No AutoCount document has been uploaded for this sales order yet.',
      },
      lines: [
        {
          id: 'nodoc-l1',
          line_no: 1,
          product_code: 'CB6633',
          description: 'CABANA S/STEEL FLOOR GRATING 6"',
          qty: '600',
          uom: 'UNIT',
          delivery_date: '2026-09-01',
          stock_location: 'BRW-BB',
          link: 'missing',
          candidate_count: 0,
          reason: 'There is no core sales order to map this line against.',
        },
        {
          id: 'nodoc-l2',
          line_no: 2,
          product_code: 'SRT382-6',
          description: 'SORENTO S/S SINK MIXER 382-6',
          qty: '40',
          uom: 'UNIT',
          delivery_date: '2026-09-15',
          stock_location: 'BRW-BB',
          link: 'missing',
          candidate_count: 0,
          reason: 'There is no core sales order to map this line against.',
        },
      ],
      exceptions: [
        {
          kind: 'header',
          message:
            'No AutoCount document has been uploaded for this sales order yet. Upload it on the AutoCount screen for this order.',
        },
      ],
      lines_total: 2,
      lines_linked: 0,
      reconciled_at: null,
    };
  }

  if (row.id === 'mock-pso-missing') {
    return {
      ...base,
      header: {
        outcome: 'linked',
        core_so_number: 'SO376202',
        reason: 'Linked to sales order SO376202.',
      },
      lines: [
        {
          id: 'missing-l1',
          line_no: 1,
          product_code: 'CB6633',
          description: 'CABANA S/STEEL FLOOR GRATING 6"',
          qty: '120',
          uom: 'UNIT',
          delivery_date: '2026-07-01',
          stock_location: 'BRW-BB',
          link: 'linked',
          candidate_count: 1,
          reason: 'Matched on product and required date 01 Jul 2026.',
        },
        {
          id: 'missing-l2',
          line_no: 2,
          product_code: 'SRT501-CP',
          description: 'SORENTO BASIN MIXER 501 CHROME',
          qty: '80',
          uom: 'UNIT',
          delivery_date: '2026-07-20',
          stock_location: 'BRW-BB',
          link: 'missing',
          candidate_count: 0,
          reason: 'The AutoCount document has no line for this item.',
        },
        {
          id: 'missing-l3',
          line_no: 3,
          product_code: 'CB2201',
          description: 'CABANA FLOOR TRAP 4"',
          qty: '200',
          uom: 'UNIT',
          delivery_date: '2026-08-05',
          stock_location: 'HQ',
          link: 'missing',
          candidate_count: 0,
          reason: 'Its previous core line is now closed, so the link was cleared.',
        },
      ],
      exceptions: [
        {
          line_no: 2,
          item_code: 'SRT501-CP',
          kind: 'missing',
          message: 'The AutoCount document has no line for this item.',
        },
        {
          line_no: 3,
          item_code: 'CB2201',
          kind: 'missing',
          message: 'Its previous core line is now closed, so the link was cleared.',
        },
        {
          item_code: 'SRT770-BK',
          kind: 'surplus',
          message:
            'On the AutoCount document and not on this sales order. Answer it in AutoCount Differences.',
        },
      ],
      lines_total: 3,
      lines_linked: 1,
      reconciled_at: '2026-08-15T07:12:00',
    };
  }

  if (row.id === 'mock-pso-ambiguous') {
    return {
      ...base,
      header: {
        outcome: 'linked',
        core_so_number: 'SO376203',
        reason: 'Linked to sales order SO376203.',
      },
      lines: [
        {
          id: 'amb-l1',
          line_no: 1,
          product_code: 'CB6633',
          description: 'CABANA S/STEEL FLOOR GRATING 6"',
          qty: '300',
          uom: 'UNIT',
          delivery_date: '2026-07-01',
          stock_location: 'BRW-BB',
          link: 'linked',
          candidate_count: 1,
          reason: 'Matched on product and required date 01 Jul 2026.',
        },
        {
          id: 'amb-l2',
          line_no: 2,
          product_code: 'SRT382-6',
          description: 'SORENTO S/S SINK MIXER 382-6',
          qty: '50',
          uom: 'UNIT',
          delivery_date: '2026-07-10',
          stock_location: 'BRW-BB',
          link: 'ambiguous',
          candidate_count: 2,
          reason: 'Two lines on the AutoCount document carry this item on 10 Jul 2026.',
        },
        {
          id: 'amb-l3',
          line_no: 3,
          product_code: 'SRT382-6',
          description: 'SORENTO S/S SINK MIXER 382-6',
          qty: '50',
          uom: 'UNIT',
          delivery_date: '2026-07-10',
          stock_location: 'HQ',
          link: 'ambiguous',
          candidate_count: 2,
          reason: 'Two lines on the AutoCount document carry this item on 10 Jul 2026.',
        },
      ],
      exceptions: [
        {
          line_no: 2,
          item_code: 'SRT382-6',
          kind: 'ambiguous',
          message:
            'Two lines on the AutoCount document carry this item on 10 Jul 2026, so neither pairing is certain.',
        },
        {
          line_no: 3,
          item_code: 'SRT382-6',
          kind: 'ambiguous',
          message:
            'Two lines on the AutoCount document carry this item on 10 Jul 2026, so neither pairing is certain.',
        },
      ],
      lines_total: 3,
      lines_linked: 1,
      reconciled_at: '2026-08-16T01:05:00',
    };
  }

  return {
    ...base,
    header: {
      outcome: 'linked',
      core_so_number: 'SO376201',
      reason: 'Linked to sales order SO376201.',
    },
    lines: [
      {
        id: 'clean-l1',
        line_no: 1,
        product_code: 'CB6633',
        description: 'CABANA S/STEEL FLOOR GRATING 6"',
        qty: '600',
        uom: 'UNIT',
        delivery_date: '2026-07-01',
        stock_location: 'BRW-BB',
        link: 'linked',
        candidate_count: 1,
        reason: 'Matched on product and required date 01 Jul 2026.',
      },
      {
        id: 'clean-l2',
        line_no: 2,
        product_code: 'SRT382-6',
        description: 'SORENTO S/S SINK MIXER 382-6',
        qty: '40',
        uom: 'UNIT',
        delivery_date: '2026-07-01',
        stock_location: 'BRW-BB',
        link: 'linked',
        candidate_count: 1,
        reason: 'Matched on product and required date 01 Jul 2026.',
      },
      {
        id: 'clean-l3',
        line_no: 3,
        product_code: 'CB2201',
        description: 'CABANA FLOOR TRAP 4"',
        qty: '200',
        uom: 'UNIT',
        delivery_date: '2026-08-05',
        stock_location: 'HQ',
        link: 'linked',
        candidate_count: 1,
        reason: 'Matched in required-date order after the exact-date pass.',
      },
      {
        id: 'clean-l4',
        line_no: 4,
        product_code: 'SRT770-BK',
        description: 'SORENTO SHOWER SET 770 BLACK',
        qty: '25',
        uom: 'SET',
        delivery_date: '2026-08-20',
        stock_location: 'HQ',
        link: 'linked',
        candidate_count: 1,
        reason: 'Matched in required-date order after the exact-date pass.',
      },
    ],
    exceptions: [],
    lines_total: 4,
    lines_linked: 4,
    reconciled_at: '2026-08-14T02:41:00',
  };
}
