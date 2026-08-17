import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import { PROJECT_SO_MOCK } from './projectSalesOrderService';
import type {
  ConfirmResult,
  ConfirmSupplyBody,
  FulfilmentPlanningListEnvelope,
  FulfilmentPlanningListParams,
  FulfilmentPlanningRow,
  ReconciliationSummary,
  SupplyFailingLine,
  SupplyProposal,
} from '../types/fulfilmentPlanning.types';
import {
  MOCK_PLANNING_ROWS,
  mockConfirmSupply,
  mockReconciliation,
  mockSupply,
} from './fulfilmentPlanningMocks';

/**
 * Fulfilment Planning: the AutoCount reconciliation of a published Project SO (Stage 1B),
 * and the supply composition CS confirms on top of it (Stage 1C).
 *
 * API CONTRACT (`documentation/plans/scm/STAGE1B-scm-front-planning-reconciliation.md`
 * section 3 and `STAGE1C-scm-front-planning-promising.md` section 6; a deviation updates
 * that file and both sides in the same change). Every route hangs off the existing
 * `/api/v1/project-sales` router, reads with `projects.projects.view`, writes with
 * `projects.projects.edit`.
 *
 *   GET  /project-sales/fulfilment-planning?page&limit&query&review_state&project_id
 *        -> { data: FulfilmentPlanningRow[], pagination: { total, page, limit } }
 *        review_state is a closed set: awaiting_reconciliation | needs_cs_review | confirmed
 *
 *   GET  /project-sales/sales-orders/{pso_id}/reconciliation -> ReconciliationSummary
 *   POST /project-sales/sales-orders/{pso_id}/reconcile      -> ReconciliationSummary
 *
 *   GET  /project-sales/sales-orders/{pso_id}/supply  -> SupplyProposal
 *   POST /project-sales/sales-orders/{pso_id}/confirm -> ConfirmResult
 *        body ConfirmSupplyBody; 409/422 -> { error, failing_lines: [{line_no, item_code,
 *        reason}] }, nothing written (AC-C02)
 *
 * An exception's `message` carries the REASON only. The screen prints the subject itself
 * from `line_no` and `item_code` ("Line 2, SRT501-CP"), so a message that repeats it reads
 * as the same fact twice.
 *
 * The reconcile POST is idempotent. The confirm POST is not a retry of a partial write:
 * it either commits every line or writes nothing at all.
 *
 * `NEXT_PUBLIC_PROJECT_SO_MOCK=1` serves `fulfilmentPlanningMocks` instead of calling any
 * of it, which is how the composition cases (reserve + buy, the hot-selling BRW cap, a
 * borrow candidate and its reason, a discontinued buy, advisory incoming, an unavailable
 * classification, an unbalanced line, a refused confirmation, the confirmed frozen view
 * and a challenged decision) are reachable while the backend for the same contract is
 * being written. The switch is the one `projectSalesOrderService` already owns, so a
 * session is either all mock or all live. Deleted when Phase 2 lands.
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
  const limit = params.limit ?? 25;
  if (PROJECT_SO_MOCK) {
    const needle = (params.query ?? '').trim().toLowerCase();
    const rows = MOCK_PLANNING_ROWS().filter((row) => {
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
  const search = buildDataGridParams(
    {
      pageIndex: (params.page ?? 1) - 1,
      pageSize: limit,
      // No `sorting`: the worklist is server-ordered by last update and offers no
      // sortable column, so there is no sort to carry.
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
  if (PROJECT_SO_MOCK) return mockReconciliation(psoId);
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
  if (PROJECT_SO_MOCK) return mockReconciliation(psoId);
  const response = await apiFetch(`${BASE}/sales-orders/${psoId}/reconcile`, {
    method: 'POST',
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to re-run the reconciliation'));
  return response.json();
}

/**
 * The composition the engine proposes for every line, its evidence, and the active
 * decision when one exists. A pure read: opening the sheet claims no stock.
 */
export async function getSupply(psoId: string): Promise<SupplyProposal> {
  if (PROJECT_SO_MOCK) return mockSupply(psoId);
  const response = await apiFetch(`${BASE}/sales-orders/${psoId}/supply`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the supply composition'));
  return response.json();
}

/**
 * A refused confirmation, carrying the lines that refused it.
 *
 * `extractApiError` answers with a string, and the 422 body's `failing_lines` is a list the
 * sheet prints line by line, so the message alone would lose exactly the part CS acts on.
 * Same shape of problem as the prompt registry's validation body.
 */
export class ConfirmSupplyError extends Error {
  readonly failingLines: SupplyFailingLine[];

  constructor(message: string, failingLines: SupplyFailingLine[] = []) {
    super(message);
    this.name = 'ConfirmSupplyError';
    this.failingLines = failingLines;
  }
}

/**
 * Confirm the whole sales order once (AC-C01). Every line commits together or none does,
 * so there is no per-line call and no partial state to resume from.
 */
export async function confirmSupply(
  psoId: string,
  body: ConfirmSupplyBody,
): Promise<ConfirmResult> {
  if (PROJECT_SO_MOCK) return mockConfirmSupply(psoId, body);
  const response = await apiFetch(`${BASE}/sales-orders/${psoId}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    // The message goes through the shared extractor like everywhere else; the clone is
    // what carries the failing lines, because a body can only be read once and the
    // extractor answers with a string.
    const clone = response.clone();
    const message = await extractApiError(response, 'Failed to confirm this sales order');
    let failingLines: SupplyFailingLine[] = [];
    try {
      const payload = (await clone.json()) as { failing_lines?: SupplyFailingLine[] };
      if (Array.isArray(payload?.failing_lines)) failingLines = payload.failing_lines;
    } catch {
      // Not JSON, so there are no failing lines to name and the message is the answer.
    }
    throw new ConfirmSupplyError(message, failingLines);
  }
  return response.json();
}
