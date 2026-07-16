/**
 * ============================================================================
 * SCM M3 — Reorder-run feature service  (Phase-2: live backend)
 * ============================================================================
 * Layering: hooks (useReorderRun) → THIS service → lib/api-client → backend.
 *
 * ── BACKEND CONTRACT ────────────────────────────────────────────────────────
 *
 * 1) Launch a run
 *    POST /api/v1/scm/reorder-runs
 *    body: {
 *      warehouse_codes: string[],          // which warehouses to plan for
 *      buy_scope: "network" | "warehouse", // aggregate vs per-warehouse
 *      budget_id?: string | null           // M4 — always null/omitted in M3
 *    }
 *    → 202 { run_id, status: "running", buy_scope, stage: <ReorderRunStage> }
 *    Enqueues the RQ `run_reorder(run_id)` task. Auth: `scm.reorder.run`.
 *
 * 2) Poll run status  (UI polls until status ∈ {completed, failed})
 *    GET /api/v1/scm/reorder-runs/{run_id}
 *    → 200 {
 *        run_id, status: "running"|"completed"|"failed",
 *        stage, buy_scope,
 *        error: string | null,               // set when status = "failed"
 *        summary: null | {                    // set when status = "completed"
 *          buy_count, disposition_count, exception_count,
 *          total_cash_impact, recommendation_count
 *        }
 *      }
 *
 * 3) Paginated recommendations for a completed run  (DataGrid)
 *    GET /api/v1/scm/reorder-runs/{run_id}/recommendations
 *        ?page&limit&sort&dir&query&type=buy|disposition|exception
 *    (query string built with `buildDataGridParams`; sort/dir are server-side)
 *    → 200 {
 *        data: ReorderRecommendation[],       // see types/reorder.types.ts
 *        pagination: { page, limit, total, total_pages }
 *      }
 *    Each row carries its FROZEN inputs (net, ROP, SS, lead_time, supplier,
 *    policy_ref, allocation, triggered_reason, confidence) per AC-M3.11 —
 *    read-only in M3 (Accept/Adjust/Dismiss + cash ranking land in M4).
 *
 * 4) Run history  (newest-first, paginated)
 *    GET /api/v1/scm/reorder-runs?page&limit
 *    → 200 {
 *        data: [{ run_id, status, buy_scope, warehouse_codes, warehouse_count,
 *                 started_at, finished_at, summary: null | ReorderRunSummary }],
 *        pagination: { page, limit, total, total_pages }
 *      }
 *    Lets the user revisit any past run: clicking one loads its summary via (2)
 *    and its recommendations via (3) WITHOUT re-running. Auth: `scm.dashboard.view`.
 * ============================================================================
 */
import type { SortingState } from '@tanstack/react-table';
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type {
  BuyScope,
  CreateReorderRunRequest,
  ReorderRecommendation,
  ReorderRun,
  ReorderRunStage,
  ReorderRunStatus,
  ReorderRunSummary,
} from '../types/reorder.types';

export interface RecommendationQuery {
  pageIndex: number;
  pageSize: number;
  /** Filter to a single type; null = all. Server-side. */
  type?: 'buy' | 'disposition' | 'exception' | null;
  searchQuery?: string;
  /** Column sort — forwarded to the backend as `sort`/`dir`. */
  sorting?: SortingState;
}

export interface RecommendationPage {
  data: ReorderRecommendation[];
  pagination: { page: number; limit: number; total: number; total_pages: number };
}

/** One row in the run-history list (newest-first). Runs are identified by time +
 *  warehouses — never the run_id (no UUIDs surface). */
export interface ReorderRunHistoryItem {
  run_id: string;
  status: ReorderRunStatus;
  buy_scope: BuyScope;
  warehouse_codes: string[];
  warehouse_count: number;
  /** Naive-UTC ISO strings — format with `formatDateTimeInMalaysia` (raw string). */
  started_at: string | null;
  finished_at: string | null;
  /** Populated once the run completed; null while running / failed. */
  summary: ReorderRunSummary | null;
}

export interface ReorderRunHistoryPage {
  data: ReorderRunHistoryItem[];
  pagination: { page: number; limit: number; total: number; total_pages: number };
}

/** Raw shape returned by POST /reorder-runs (202). */
interface ReorderRunAcceptedDto {
  run_id: string;
  status: ReorderRunStatus;
  buy_scope: string;
  stage: string;
}

/** Raw shape returned by GET /reorder-runs/{id}. */
interface ReorderRunStatusDto {
  run_id: string;
  status: ReorderRunStatus;
  stage: string | null;
  buy_scope: string | null;
  error: string | null;
  summary: ReorderRunSummary | null;
}

const DEFAULT_STAGE: ReorderRunStage = 'resolving_policies';

/** Launch a run. Returns a running run record the hook then polls. */
export async function createReorderRun(req: CreateReorderRunRequest): Promise<ReorderRun> {
  const res = await apiFetch('/api/v1/scm/reorder-runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      warehouse_codes: req.warehouse_codes,
      buy_scope: req.buy_scope,
      budget_id: req.budget_id ?? null,
    }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to start planning run'));
  const dto = (await res.json()) as ReorderRunAcceptedDto;
  return {
    run_id: dto.run_id,
    status: dto.status,
    stage: (dto.stage as ReorderRunStage) ?? DEFAULT_STAGE,
    buy_scope: (dto.buy_scope as BuyScope) ?? req.buy_scope,
    summary: null,
    error: null,
  };
}

/** Poll a run's status. `summary` populates on completed; `error` on failed. */
export async function getReorderRun(runId: string): Promise<ReorderRun> {
  const res = await apiFetch(`/api/v1/scm/reorder-runs/${encodeURIComponent(runId)}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load run status'));
  const dto = (await res.json()) as ReorderRunStatusDto;
  return {
    run_id: dto.run_id,
    status: dto.status,
    stage: (dto.stage as ReorderRunStage) ?? DEFAULT_STAGE,
    buy_scope: (dto.buy_scope as BuyScope) ?? 'network',
    summary: dto.summary ?? null,
    error: dto.error ?? null,
  };
}

/** Paginated recommendations for the results grid (server-side page/sort/filter). */
export async function getRecommendations(
  runId: string,
  q: RecommendationQuery,
): Promise<RecommendationPage> {
  const params = buildDataGridParams(
    {
      pageIndex: q.pageIndex,
      pageSize: q.pageSize,
      sorting: q.sorting ?? [],
      searchQuery: q.searchQuery ?? '',
    },
    q.type ? { type: q.type } : {},
  );
  const res = await apiFetch(
    `/api/v1/scm/reorder-runs/${encodeURIComponent(runId)}/recommendations?${params}`,
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load recommendations'));
  return (await res.json()) as RecommendationPage;
}

/** Newest-first paginated run history (drives the Run history panel). */
export async function listReorderRuns(
  page: number,
  limit: number,
): Promise<ReorderRunHistoryPage> {
  const params = buildDataGridParams({
    pageIndex: page - 1,
    pageSize: limit,
    sorting: [],
    searchQuery: '',
  });
  const res = await apiFetch(`/api/v1/scm/reorder-runs?${params}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load run history'));
  return (await res.json()) as ReorderRunHistoryPage;
}
