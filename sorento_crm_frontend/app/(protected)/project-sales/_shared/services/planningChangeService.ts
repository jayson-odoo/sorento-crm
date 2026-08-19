/**
 * ============================================================================
 * Planning changes - feature service (`PLAN-so-book-diff-replanning.md` section 3)
 * ============================================================================
 * Layering: UI -> hooks (`usePlanningChanges`) -> THIS service -> lib/api-client -> backend.
 *
 * ── CONTRACT ─────────────────────────────────────────────────────────────────
 * All endpoints mount under `require_module_enabled_with_api_key("projects")`, reads on
 * `projects.projects.view`, the two writes on `projects.projects.edit`.
 *
 *   GET  /api/v1/project-sales/planning-changes                              (AC-R10)
 *        query: page, limit, query, state ('pending' | 'applied'), sort, dir
 *        -> flat { data, total, page, limit } (DataGrid contract, NOT the nested envelope)
 *   GET  /api/v1/project-sales/planning-changes/{batch_id}                   (AC-R02)
 *   PUT  /api/v1/project-sales/planning-changes/{batch_id}/rows/{row_id}     (AC-R04)
 *        body UpdatePlanningChangeRowBody { decision, composition? }
 *        `composition` is REQUIRED when `decision === 'amend'` (422 otherwise); `confirm`
 *        derives its own composition from the row's `proposal` server-side.
 *   POST /api/v1/project-sales/planning-changes/{batch_id}/apply             (AC-R05)
 *        -> ApplyPlanningChangesResult { applied_orders, failed_orders, already_applied }
 *
 * The upload confirmation response carries a batch pointer under
 * `result.upload.planning_change_batch` on the import job it queued (read on the import job
 * page, not fetched from this service) - see `outstandingImportService.ts`.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type {
  ApplyPlanningChangesResult,
  PlanningChangeBatch,
  PlanningChangeListEnvelope,
  PlanningChangeListParams,
  PlanningChangeRow,
  UpdatePlanningChangeRowBody,
} from '../types/planningChange.types';

const BASE = '/api/v1/project-sales';

export async function listPlanningChangeBatches(
  params: PlanningChangeListParams = {},
): Promise<PlanningChangeListEnvelope> {
  const search = buildDataGridParams(
    {
      pageIndex: (params.page ?? 1) - 1,
      pageSize: params.limit ?? 25,
      sorting: params.sort ? [{ id: params.sort, desc: params.dir === 'desc' }] : [],
      searchQuery: params.query ?? '',
    },
    { state: params.state },
  );
  const response = await apiFetch(`${BASE}/planning-changes?${search.toString()}`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load planning changes'));
  return response.json();
}

export async function getPlanningChangeBatch(batchId: string): Promise<PlanningChangeBatch> {
  const response = await apiFetch(
    `${BASE}/planning-changes/${encodeURIComponent(batchId)}`,
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the batch'));
  return response.json();
}

export async function updatePlanningChangeRow(
  batchId: string,
  rowId: string,
  body: UpdatePlanningChangeRowBody,
): Promise<PlanningChangeRow> {
  const response = await apiFetch(
    `${BASE}/planning-changes/${encodeURIComponent(batchId)}/rows/${encodeURIComponent(rowId)}`,
    { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to save the decision'));
  return response.json();
}

export async function applyPlanningChanges(
  batchId: string,
): Promise<ApplyPlanningChangesResult> {
  const response = await apiFetch(
    `${BASE}/planning-changes/${encodeURIComponent(batchId)}/apply`,
    { method: 'POST' },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to apply the planning changes'));
  return response.json();
}
