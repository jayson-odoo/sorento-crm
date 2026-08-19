import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { PlanListEnvelope, PlanListParams, PlanRow } from '../types/fulfilmentPlanning.types';

/**
 * The Plans page (PLAN-demo-followups-19aug-ladder-v2 D1).
 *
 * "Is the plan stored, how do I review it" - the captain, after the 19 August demo. Every
 * confirmed sales-order composition, one row per revision, cross-order.
 *
 * API CONTRACT:
 *
 *   GET /project-sales/plans?page&limit&query&state&agent_code&sort&dir
 *       -> { data: PlanRow[], pagination: { total, page, limit } }
 *
 *       `state` is a closed set (active | superseded | challenged), defaulting server-side
 *       to `active` - the plan is asking what is committed NOW, not the whole revision
 *       history a line has ever carried. `query` matches the sales-order number, the
 *       customer name and the agent code - the three the row itself prints.
 *
 * Same `/api/v1/project-sales` router as the rest of fulfilment planning, same
 * `projects.projects.view` read permission, no new permission introduced.
 */

const BASE = '/api/v1/project-sales';

function normaliseEnvelope(body: unknown, fallbackLimit: number): PlanListEnvelope {
  const raw = (body ?? {}) as {
    data?: PlanRow[];
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

export async function listPlans(params: PlanListParams = {}): Promise<PlanListEnvelope> {
  const limit = params.limit ?? 25;
  const search = buildDataGridParams(
    {
      pageIndex: (params.page ?? 1) - 1,
      pageSize: limit,
      sorting: params.sort ? [{ id: params.sort, desc: params.dir === 'desc' }] : undefined,
      searchQuery: params.query ?? '',
    },
    {
      state: params.state,
      agent_code: params.agent_code,
    },
  );
  const response = await apiFetch(`${BASE}/plans?${search.toString()}`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the plans list'));
  return normaliseEnvelope(await response.json(), limit);
}
