import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type {
  FulfilmentPlanningListEnvelope,
  FulfilmentPlanningListParams,
  FulfilmentPlanningRow,
  ReconciliationSummary,
} from '../types/fulfilmentPlanning.types';

/**
 * Fulfilment Planning: the AutoCount reconciliation of a published Project SO (Stage 1B).
 *
 * API CONTRACT (`documentation/plans/scm/STAGE1B-scm-front-planning-reconciliation.md`
 * section 3; a deviation updates that file and both sides in the same change). All three
 * routes hang off the existing
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
  const response = await apiFetch(`${BASE}/sales-orders/${psoId}/reconcile`, {
    method: 'POST',
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to re-run the reconciliation'));
  return response.json();
}
