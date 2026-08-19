/**
 * ============================================================================
 * Planning changes - feature service (`PLAN-so-book-diff-replanning.md` section 3)
 * ============================================================================
 * Layering: UI -> hooks (`usePlanningChanges`) -> THIS service -> lib/api-client -> backend.
 *
 * PHASE 1 STUB - every function below serves an in-memory copy of the fixture batches with a
 * small fake latency, so the batch page, the list page and the upload card can be built and
 * reviewed before any backend endpoint exists. Replace with `apiFetch` + `extractApiError`
 * calls in Phase 2, matching the contract exactly; nothing above this file (hooks, components)
 * should need to change.
 *
 * ── PHASE-2 BACKEND CONTRACT ────────────────────────────────────────────────
 * All endpoints mount under `require_module_enabled_with_api_key("projects")`.
 *
 * 1) List batches, newest first (AC-R10)
 *    GET /api/v1/project-sales/planning-changes
 *    query: page, limit, query, state ('pending' | 'applied'), sort, dir
 *    -> 200 { data: PlanningChangeBatchSummary[], total, page, limit }   (DataGrid contract)
 *    Auth: `projects.projects.view`.
 *
 * 2) One batch, as it read at step 1 plus what was applied
 *    GET /api/v1/project-sales/planning-changes/{batch_id}
 *    -> 200 PlanningChangeBatch
 *    Auth: `projects.projects.view`.
 *
 * 3) The one decision per row (AC-R04). Writes nothing else.
 *    PUT /api/v1/project-sales/planning-changes/{batch_id}/rows/{row_id}
 *    body UpdatePlanningChangeRowBody { decision }
 *    -> 200 PlanningChangeRow
 *    Auth: `projects.projects.view`.
 *
 * 4) Apply the accepted rows, atomically per order (AC-R05)
 *    POST /api/v1/project-sales/planning-changes/{batch_id}/apply
 *    -> 200 ApplyPlanningChangesResult { applied_orders, failed_orders, already_applied }
 *    Auth: `projects.projects.view` (writes go through the same supply-confirmation path
 *    Fulfilment Planning uses, so no separate "manage" permission is introduced here).
 *
 * 5) The upload confirmation response gains a batch pointer
 *    (carried on the SCM outstanding-orders upload preview/apply response, see
 *    `outstandingImportService.ts`): `planning_change_batch: { id, order_count, line_count }
 *    | null`. Read there, not fetched from this service.
 *
 * ── FACTS AND RESULT (captain review, 19 Aug 2026) ─────────────────────────
 * `PlanningChangeRow.facts` carries its own proof, not a bare boolean: `dealer_hot_selling`
 * and `project_hot_selling` are `{ value, where }` (ABC-A by delivered quantity on that demand
 * pool in the last 365 days, at the locations named); `within_reserve_window` is
 * `{ value, window_days, new_date, window_end }`; `buy_actioned` is `{ value, po_number }`.
 * `PlanningChangeOrder` carries `is_adopted` + `core_sales_order_id` + `project_id` so the SO
 * number links to its own document. `PlanningChangeBatch.source` carries `kind` +
 * `import_job_id` (the upload's trigger, linkable to `/system-management/import-jobs/{id}`).
 * `PlanningChangeBatch.result` (`null` until Apply runs) carries what Apply did: orders
 * revised/failed, Order Inquiry rows changed, lines back on the board, whether purchasing was
 * told - all read back as data on the batch page after Apply, and the fixture batch `pcb-0`.
 * ============================================================================
 */
import {
  MOCK_PLANNING_CHANGE_BATCHES,
  MOCK_PLANNING_CHANGE_BATCH_APPLIED,
  MOCK_PLANNING_CHANGE_BATCH_PENDING,
} from '../__mocks__/planningChanges';
import type {
  ApplyPlanningChangesResult,
  PlanningChangeBatch,
  PlanningChangeListEnvelope,
  PlanningChangeListParams,
  PlanningChangeRow,
  UpdatePlanningChangeRowBody,
} from '../types/planningChange.types';

/** A small fixed delay so a loading state is visible - never random, per the repo's own idiom. */
const MOCK_DELAY_MS = 300;
const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** In-memory copy so a row-decision write in one call is read back by the next. */
const STORE = new Map<string, PlanningChangeBatch>(
  [MOCK_PLANNING_CHANGE_BATCH_PENDING, MOCK_PLANNING_CHANGE_BATCH_APPLIED].map((batch) => [
    batch.id,
    structuredClone(batch),
  ]),
);

function summariesFromStore() {
  return MOCK_PLANNING_CHANGE_BATCHES.map((summary) => {
    const batch = STORE.get(summary.id);
    if (!batch) return summary;
    return {
      ...summary,
      applied_at: batch.applied_at,
      applied_by_name: batch.applied_by_name,
      pending_count: batch.orders.reduce(
        (total, order) =>
          total + order.rows.filter((row) => row.applied_state === 'pending').length,
        0,
      ),
      failed_count: batch.orders.reduce(
        (total, order) =>
          total + order.rows.filter((row) => row.applied_state === 'failed').length,
        0,
      ),
    };
  }).sort((left, right) => right.created_at.localeCompare(left.created_at));
}

export async function listPlanningChangeBatches(
  params: PlanningChangeListParams = {},
): Promise<PlanningChangeListEnvelope> {
  await delay(MOCK_DELAY_MS);
  let rows = summariesFromStore();
  if (params.state === 'pending') rows = rows.filter((row) => !row.applied_at);
  if (params.state === 'applied') rows = rows.filter((row) => Boolean(row.applied_at));
  const needle = params.query?.trim().toLowerCase();
  if (needle) {
    rows = rows.filter(
      (row) =>
        row.source.file_name.toLowerCase().includes(needle) ||
        row.created_by_name.toLowerCase().includes(needle),
    );
  }
  return { data: rows, total: rows.length, page: params.page ?? 1, limit: params.limit ?? 25 };

  // Phase 2:
  // const search = buildDataGridParams(
  //   { pageIndex: (params.page ?? 1) - 1, pageSize: params.limit ?? 25, sorting: [], searchQuery: params.query ?? '' },
  //   { state: params.state },
  // );
  // const response = await apiFetch(`/api/v1/project-sales/planning-changes?${search.toString()}`);
  // if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load planning changes'));
  // return response.json();
}

export async function getPlanningChangeBatch(batchId: string): Promise<PlanningChangeBatch> {
  await delay(MOCK_DELAY_MS);
  const batch = STORE.get(batchId);
  if (!batch) throw new Error('This planning change batch could not be found.');
  return structuredClone(batch);

  // Phase 2:
  // const response = await apiFetch(`/api/v1/project-sales/planning-changes/${encodeURIComponent(batchId)}`);
  // if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load the batch'));
  // return response.json();
}

export async function updatePlanningChangeRow(
  batchId: string,
  rowId: string,
  body: UpdatePlanningChangeRowBody,
): Promise<PlanningChangeRow> {
  await delay(MOCK_DELAY_MS);
  const batch = STORE.get(batchId);
  if (!batch) throw new Error('This planning change batch could not be found.');
  let updated: PlanningChangeRow | undefined;
  for (const order of batch.orders) {
    const row = order.rows.find((entry) => entry.id === rowId);
    if (row) {
      row.decision = body.decision;
      updated = row;
    }
  }
  if (!updated) throw new Error('This row could not be found.');
  return structuredClone(updated);

  // Phase 2:
  // const response = await apiFetch(
  //   `/api/v1/project-sales/planning-changes/${encodeURIComponent(batchId)}/rows/${encodeURIComponent(rowId)}`,
  //   { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
  // );
  // if (!response.ok) throw new Error(await extractApiError(response, 'Failed to save the decision'));
  // return response.json();
}

export async function applyPlanningChanges(
  batchId: string,
): Promise<ApplyPlanningChangesResult> {
  await delay(MOCK_DELAY_MS);
  const batch = STORE.get(batchId);
  if (!batch) throw new Error('This planning change batch could not be found.');
  if (batch.applied_at) {
    return {
      applied_orders: batch.orders.map((order) => order.so_number),
      failed_orders: [],
      already_applied: true,
    };
  }
  const appliedOrders: string[] = [];
  const ordersRevised: { so_number: string; revision_no: number }[] = [];
  const inquiryCounts = new Map<string, number>();
  let linesReplanned = 0;
  for (const order of batch.orders) {
    let orderApplied = false;
    for (const row of order.rows) {
      if (row.applied_state !== 'pending') continue;
      if (row.decision !== 'accept') continue;
      row.applied_state = 'applied';
      orderApplied = true;
      // A `keep` leaves the board untouched; every other verb moves a line back onto it.
      if (row.suggested !== 'keep') linesReplanned += 1;
      for (const inquiry of row.inquiry_rows) {
        inquiryCounts.set(inquiry.verb, (inquiryCounts.get(inquiry.verb) ?? 0) + 1);
      }
    }
    appliedOrders.push(order.so_number);
    if (orderApplied) {
      order.revision_no += 1;
      ordersRevised.push({ so_number: order.so_number, revision_no: order.revision_no });
    }
  }
  batch.applied_at = new Date().toISOString();
  batch.applied_by_name = 'You';
  batch.result = {
    orders_revised: ordersRevised,
    orders_failed: [],
    inquiry_rows_changed: Array.from(inquiryCounts, ([verb, count]) => ({ verb, count })),
    lines_replanned: linesReplanned,
    purchasing_notified: inquiryCounts.size > 0,
  };
  return { applied_orders: appliedOrders, failed_orders: [], already_applied: false };

  // Phase 2:
  // const response = await apiFetch(`/api/v1/project-sales/planning-changes/${encodeURIComponent(batchId)}/apply`, { method: 'POST' });
  // if (!response.ok) throw new Error(await extractApiError(response, 'Failed to apply the planning changes'));
  // return response.json();
}
