/**
 * ============================================================================
 * SCM M3 - Reorder-run feature service  (Phase-2: live backend)
 * ============================================================================
 * Layering: hooks (useReorderRun) → THIS service → lib/api-client → backend.
 *
 * ── BACKEND CONTRACT ────────────────────────────────────────────────────────
 *
 * 1) Launch a run
 *    POST /api/v1/scm/reorder-runs
 *    body: {
 *      warehouse_codes: string[],          // which warehouses to plan for
 *      product_codes?: string[],           // AC-B8a: omitted/empty = ALL products.
 *                                          //   Human codes. Phase 2 adds the field to
 *                                          //   the backend schema; sent only when the
 *                                          //   user narrowed the run.
 *      budget_id?: string | null           // M4 - always null/omitted in M3
 *    }
 *    Planning scope is fixed server-side (M8-D5) - no `buy_scope` in the request.
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
 * 2b) STAGE 2 additions to the run and recommendation shapes (front planning)
 *
 *    The run record (create, poll, today, history) carries:
 *      decision_grain: 'product' | 'location' | null   stamped ONCE at creation from
 *                                                      the admin plan-grain policy
 *                                                      setting; never changed by a
 *                                                      later edit of that setting, and
 *                                                      NULL only on a legacy run
 *      front_planning_contract_version: number | null  `1` on a front-planning run,
 *                                                      NULL on a legacy one. Decision
 *                                                      writes are rejected when it is
 *                                                      NULL, and when the write's grain
 *                                                      differs from `decision_grain`
 *                                                      (AC-F01 / AC-F09 / AC-F10).
 *
 *    Each recommendation row carries its frozen demand-channel split:
 *      project_need, retail_need: number | null      (NULL on legacy)
 *          project_need is the un-linked remainder of raised Order Inquiry rows - the leg
 *          that bypasses the reorder trigger, and since P3 the whole of project demand.
 *          There is no third channel: a sales order with no class reads as retail.
 *      decisions_read_only: boolean                  true when the run is decided at
 *                                                    the other grain, so the location
 *                                                    row is a read and drill row
 *    Shared supply - stock, incoming SPO, PO, reorder level - stays a SINGLE value per
 *    product-location and gains no channel dimension (AC-F07).
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
 *    policy_ref, allocation, triggered_reason, confidence) per AC-M3.11 -
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
import type { CoverScope, CoverSource } from '../lib/coverPlan';
import type { LevelSuggestionsPayload } from '../lib/levelSuggestion';
import type { EconomicsPayload } from '../lib/productHealth';
import type { PoReceipt } from '../lib/poCover';
import type { PriceHistoryPayload } from '../lib/priceAdvice';
import type { PurchaseTrendPayload } from '../lib/purchaseTrend';
import type { TrajectoryPayload } from '../lib/trajectory';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { PlanGrain } from '../lib/planGrain';
import type {
  PlanRowDecision,
  PlanRowDecisionListResponse,
  RecordPlanRowDecisionPayload,
} from '../types/decisions.types';
import type {
  BuyScope,
  CreateReorderRunRequest,
  ReorderRecommendation,
  ReorderRun,
  ReorderRunStage,
  ReorderRunStatus,
  ReorderRunSummary,
} from '../types/reorder.types';
import {
  DEFAULT_BUDGET,
  MOCK_BUY_RECS,
  TOTAL_BUY_CASH,
  computeFunding,
} from '../lib/reorderCashMock';

/**
 * ── M4 CASH CO-PILOT · PHASE-1 FLAG ─────────────────────────────────────────
 * `USE_M4_MOCKS = true` runs the WHOLE reorder page off the deterministic cash
 * mock (`lib/reorderCashMock.ts`) - no backend needed - so the budget → funded /
 * deferred interaction can be prototyped and verified in isolation. Phase 2
 * flips this to false; the run + read paths return to the live M3 endpoints and
 * the M4 cash fields arrive from the two NEW endpoints documented below.
 *
 * ── M4 PHASE-2 BACKEND CONTRACT (NEW; mounted under
 *    require_module_enabled_with_api_key("scm")) ─────────────────────────────
 *
 *  A) Recommendations WITH live funding for a budget (drives the slider what-if)
 *     GET /api/v1/scm/reorder-runs/{run_id}/recommendations?budget=X&type=buy
 *       → 200 {
 *           data: ReorderRecommendation[],   // buy rows carry the M4 fields:
 *             rank, rank_score, rank_factors, cash_impact, unit_cost,
 *             days_to_stockout, funding_status ∈ {funded, deferred, needs_cost}
 *           pagination: { page, limit, total, total_pages }
 *         }
 *     `budget` re-runs the greedy skip-overflow allocation (`computeFunding`)
 *     server-side over the FROZEN rank_score - no engine re-run. Uncosted buys
 *     (cash_impact null) are NOT cash-ranked (M4-D16): they return
 *     funding_status = `needs_cost` and never fund/defer or touch the budget.
 *     Omitting budget returns funding_status = null (unallocated). Cash
 *     ranking/funding applies to `type=buy` only; disposition/exception rows
 *     never carry cash fields. Auth: `scm.dashboard.view`.
 *
 *  B) Persist the chosen budget + funding to the run ("Apply budget")
 *     PUT /api/v1/scm/reorder-runs/{run_id}/budget   body { budget: number }
 *       → 200 { run_id, budget, funded_count, deferred_count, needs_cost_count,
 *               funded_cash, deferred_cash }
 *     Freezes funding_status onto each recommendation + stores the budget on the
 *     run so a shared run shows one funded set. Auth: `scm.reorder.run`.
 * ────────────────────────────────────────────────────────────────────────────
 */
// M4 Slice B (Phase 1): run the reorder page off the deterministic mock so a
// mock run + recommendations exist to exercise the decision layer + draft-PO
// flow with no backend. Phase 2 flips BOTH this and `USE_SLICE_B_MOCKS` to false.
export const USE_M4_MOCKS = false;

/** Stable id for the single mock run served while USE_M4_MOCKS is on. */
const MOCK_RUN_ID = 'mock-run-m4';

/** The mock run's roll-up (buy-only for this cash slice; no dispositions). */
const MOCK_SUMMARY: ReorderRunSummary = {
  buy_count: MOCK_BUY_RECS.length,
  disposition_count: 0,
  exception_count: 0,
  total_cash_impact: TOTAL_BUY_CASH,
  recommendation_count: MOCK_BUY_RECS.length,
};

function mockRun(): ReorderRun {
  return {
    run_id: MOCK_RUN_ID,
    status: 'completed',
    stage: 'writing_recommendations',
    buy_scope: 'warehouse',
    summary: MOCK_SUMMARY,
    error: null,
  };
}

export interface RecommendationQuery {
  pageIndex: number;
  pageSize: number;
  /** Filter to a single type; null = all. Server-side. */
  type?: 'buy' | 'covered' | 'disposition' | 'exception' | 'needs_level' | null;
  searchQuery?: string;
  /** Column sort - forwarded to the backend as `sort`/`dir`. */
  sorting?: SortingState;
}

export interface RecommendationPage {
  data: ReorderRecommendation[];
  pagination: { page: number; limit: number; total: number; total_pages: number };
}

/** One row in the run-history list (newest-first). Runs are identified by time +
 *  warehouses - never the run_id (no UUIDs surface). */
export interface ReorderRunHistoryItem {
  run_id: string;
  status: ReorderRunStatus;
  buy_scope: BuyScope;
  /**
   * The grain this run was STAMPED with at creation, from the admin plan-grain
   * policy setting (AC-F01). It never changes for the run, so a past run opened
   * later still reads the grain its decisions were taken at, whatever the policy
   * says today. NULL on a legacy run.
   */
  decision_grain?: PlanGrain | null;
  /** `1` on a front-planning run, NULL on a legacy one (AC-F10). */
  front_planning_contract_version?: number | null;
  warehouse_codes: string[];
  warehouse_count: number;
  /** Naive-UTC ISO strings - format with `formatDateTimeInMalaysia` (raw string). */
  started_at: string | null;
  finished_at: string | null;
  /** Populated once the run completed; null while running / failed. */
  summary: ReorderRunSummary | null;
  /**
   * The "Plan until" cutoff this run was launched with (`YYYY-MM-DD`), or null when it
   * carried none (every run has always planned every open SO line, unchanged).
   */
  plan_horizon_date?: string | null;
  /**
   * The scheduled daily run rather than one a person started (`reorder_run.created_by IS
   * NULL` - `task_scheduler._reorder_plan_tick` passes no actor). Drives the "daily" badge
   * on the plans list.
   */
  is_scheduled?: boolean;
  /**
   * The run covers EVERY active warehouse. A plan launched with no warehouse scope stores
   * them all, so without this the column reads "60 warehouses" for what the buyer asked
   * for as "all" - and only the backend knows how many active ones there are.
   */
  is_all_warehouses?: boolean;
  /**
   * The product SCOPE this run was launched with, or null when it narrowed to nothing (the
   * daily run plans every product). Distinct from `summary.recommendation_count`, which
   * counts rows.
   */
  product_count?: number | null;
  /**
   * How many products the run actually wrote rows for - the denominator of the Decided
   * column. `product_count` above is the scope and is null on the daily run, which would
   * otherwise leave the most common plan reading "12 of -".
   */
  planned_product_count?: number | null;
  /** Products with a decision recorded against them - the "x" of the Decided column (R14). */
  decided_product_count?: number | null;
  /** Products already confirmed into a draft purchase order - drives the Confirmed status. */
  confirmed_product_count?: number | null;
}

export interface ReorderRunHistoryPage {
  data: ReorderRunHistoryItem[];
  pagination: { page: number; limit: number; total: number; total_pages: number };
}

/** The run the page opens to (M8-D3/D4): today's scheduled snapshot when present,
 *  else the most-recent completed run. `is_today` distinguishes the two so the
 *  header reads "Today's plan" vs that run's date+time. Same row shape as history. */
export interface TodayRun extends ReorderRunHistoryItem {
  is_today: boolean;
  /** A plan started today that has not finished. Independent of the run returned, which is
   *  always a completed one while any completed one exists - so the page keeps the last
   *  usable snapshot on screen and says a newer plan is being built. */
  in_progress: boolean;
}

/** Load the default run for the page - `null` when no run exists yet (fresh
 *  install → empty page + Manual plan). Never throws on an empty body. */
export async function getTodayRun(): Promise<TodayRun | null> {
  const res = await apiFetch('/api/v1/scm/reorder-runs/today');
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load today’s plan'));
  const body = (await res.json()) as TodayRun | null;
  // The run carries its own stamped `decision_grain` /
  // `front_planning_contract_version` (AC-F01).
  return body ?? null;
}

/** Open demand the plan cannot net, because the sales-order line names no warehouse.
 *
 *  Planning nets per product AND location, so an unlocated line produces no
 *  recommendation. Reported so the page can say why a product with real committed demand
 *  is absent from the plan. */
export interface UnlocatedDemand {
  lines: number;
  products: number;
  quantity: number;
  sample: { product_code: string; quantity: number }[];
}

/** GET /api/v1/scm/reorder-runs/unlocated-demand */
export async function getUnlocatedDemand(): Promise<UnlocatedDemand> {
  const res = await apiFetch('/api/v1/scm/reorder-runs/unlocated-demand');
  if (!res.ok) {
    throw new Error(await extractApiError(res, 'Failed to load unlocated demand'));
  }
  return res.json();
}

export interface SetAsideDemand {
  orders: number;
  lines: number;
  quantity: number;
  sample: { so_number: string; who: string | null; quantity: number }[];
}

/**
 * GET /api/v1/scm/reorder-runs/set-aside-demand
 *
 * Project demand the plan did NOT count, because no Order Inquiry named it (S13b). The
 * report that keeps the demand split from reading as demand silently going missing.
 */
export async function getSetAsideDemand(): Promise<SetAsideDemand> {
  const res = await apiFetch('/api/v1/scm/reorder-runs/set-aside-demand');
  if (!res.ok) {
    throw new Error(await extractApiError(res, 'Failed to load set-aside demand'));
  }
  return res.json();
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
  decision_grain?: PlanGrain | null;
  front_planning_contract_version?: number | null;
  plan_horizon_date?: string | null;
  /** When the engine started. The plan page's header reads "Plan dd/mm/yyyy HH:mm" off
   *  it (C1) and this response is the only thing that page reads. */
  started_at?: string | null;
}

const DEFAULT_STAGE: ReorderRunStage = 'resolving_policies';

/** Launch a run. Returns a running run record the hook then polls. */
export async function createReorderRun(req: CreateReorderRunRequest): Promise<ReorderRun> {
  if (USE_M4_MOCKS) return mockRun(); // completes instantly - mock has no worker
  const res = await apiFetch('/api/v1/scm/reorder-runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      // Always sent, empty list included: the backend's `_resolve_warehouse_ids` reads a
      // falsy scope as EVERY active warehouse (`if warehouse_codes:` ... else every active
      // one), so `[]` is how "all warehouses" is expressed on the wire (P1). Unlike
      // `product_codes` the key has always been present, so sending it empty - rather than
      // omitting it - is what keeps an unnarrowed run byte-identical to before.
      warehouse_codes: req.warehouse_codes,
      budget_id: req.budget_id ?? null,
      include_market: req.include_market ?? false,
      // Product scope (AC-B8a) is sent ONLY when the user narrowed the run. Empty
      // means every product, and omitting the key keeps the request byte-identical
      // to what the backend accepts today, so adding the picker cannot change an
      // unnarrowed run.
      ...(req.product_codes?.length ? { product_codes: req.product_codes } : {}),
      // "Plan until" (captain, 20 Aug). Omitted when empty, same reasoning: a run that
      // never set a horizon must send a byte-identical request to before this existed.
      ...(req.plan_horizon_date ? { plan_horizon_date: req.plan_horizon_date } : {}),
    }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to start planning run'));
  const dto = (await res.json()) as ReorderRunAcceptedDto;
  return {
    run_id: dto.run_id,
    status: dto.status,
    stage: (dto.stage as ReorderRunStage) ?? DEFAULT_STAGE,
    buy_scope: (dto.buy_scope as BuyScope) ?? 'network',
    summary: null,
    error: null,
  };
}

/** Poll a run's status. `summary` populates on completed; `error` on failed. */
export async function getReorderRun(runId: string): Promise<ReorderRun> {
  if (USE_M4_MOCKS) return mockRun();
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
    // The run carries its OWN stamped grain and cut-off (AC-F01), so the plan page reads
    // the run in front of it rather than today's policy.
    decision_grain: dto.decision_grain ?? null,
    front_planning_contract_version: dto.front_planning_contract_version ?? null,
    plan_horizon_date: dto.plan_horizon_date ?? null,
    started_at: dto.started_at ?? null,
  };
}

/** DEMO / ADMIN reset - roll a run's decisions back to as-generated (clears every
 *  accept/reject/adjust + the draft POs they staged) so the flow can be re-demoed.
 *  Confirmed (active) POs are untouched. Returns what was cleared. */
export async function resetRunDecisions(
  runId: string,
): Promise<{
  run_id: string;
  decisions_cleared: number;
  overrides_cleared: number;
  /** S16: row decisions (accept/adjust/reject's own row-level cousin) reset alongside
   *  everything else this clears. */
  plan_row_decisions_cleared?: number;
}> {
  const res = await apiFetch(
    `/api/v1/scm/reorder-runs/${encodeURIComponent(runId)}/reset-decisions`,
    { method: 'POST' },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to reset the plan'));
  return res.json();
}

/**
 * S16 (captain, 21 Aug, 3rd time requested): record the row decision directly on a
 * recommendation - buy / use stock / use PO / skip, or a mixture. Works on any
 * decidable rec_type (buy, covered, needs_level, disposition), and on a product-grain
 * grouped row is called once per MEMBER recommendation id, exactly the way
 * `setMoqOverride` already fans a MOQ edit out - this route never needs to know about
 * grouping.
 */
export async function recordPlanRowDecision(
  recId: string,
  payload: RecordPlanRowDecisionPayload,
): Promise<PlanRowDecision> {
  const res = await apiFetch(`/api/v1/scm/recommendations/${recId}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to record the decision'));
  return res.json();
}

/** Withdraw a row decision back to undecided. Idempotent - clearing an already-
 *  undecided row is a no-op. */
export async function clearPlanRowDecision(recId: string): Promise<{ cleared: boolean }> {
  const res = await apiFetch(`/api/v1/scm/recommendations/${recId}/decision`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to clear the decision'));
  return res.json();
}

/**
 * Every persisted row decision on a run, plus the "N of Total made" header's own
 * decided/total counts - computed server-side off what is actually persisted, never
 * off client session state.
 */
export async function getPlanRowDecisions(runId: string): Promise<PlanRowDecisionListResponse> {
  const res = await apiFetch(`/api/v1/scm/reorder-runs/${runId}/plan-row-decisions`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the decisions'));
  const body = (await res.json()) as Partial<PlanRowDecisionListResponse>;
  return {
    data: body.data ?? [],
    decided_count: body.decided_count ?? 0,
    total_count: body.total_count ?? 0,
  };
}

/** Paginated recommendations for the results grid (server-side page/sort/filter). */
export async function getRecommendations(
  runId: string,
  q: RecommendationQuery,
): Promise<RecommendationPage> {
  if (USE_M4_MOCKS) {
    // Cash-view buy rows are served whole via getBuyRecommendationsForCash; the
    // paginated grid is only used for non-buy types here (none in the mock).
    const rows = q.type === 'buy' || !q.type ? MOCK_BUY_RECS : [];
    const start = q.pageIndex * q.pageSize;
    return {
      data: rows.slice(start, start + q.pageSize),
      pagination: {
        page: q.pageIndex + 1,
        limit: q.pageSize,
        total: rows.length,
        total_pages: Math.max(1, Math.ceil(rows.length / q.pageSize)),
      },
    };
  }
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
  // The frozen location facts carry their own demand-channel split (AC-F07).
  return (await res.json()) as RecommendationPage;
}

/**
 * The FULL disposition (Stock allocation) recommendation set for a run, unpaginated.
 * The Stock allocation view (M8-F18) splits these into actionable (Discontinue /
 * Promote) vs FYI "hold" client-side, and the tile counts ONLY the actionable subset
 * - so an accurate count needs every row, not a page. A run can carry >1000 hold rows
 * (past the endpoint's page cap) with the few actionable rows scattered alphabetically,
 * so we page through at the 1000-row cap until the whole set is fetched. Cached per run.
 */
export async function getAllDispositionRecommendations(
  runId: string,
): Promise<ReorderRecommendation[]> {
  return fetchEveryPage(runId, 'disposition');
}

/**
 * Every page of one recommendation type, in run order, with pages 2..N fetched TOGETHER.
 *
 * Page 1 is awaited alone because it is what reports `total_pages` - there is no way to know
 * how many pages exist without it. Every remaining page is then requested in parallel, which
 * is the whole point: they have no dependency on each other, and awaiting them one at a time
 * turned a plan into a staircase of round trips. Measured on the live 4,634-row run (2,150
 * buy + 2,092 disposition, so three pages of each), the six recommendation requests finished
 * in sequence at 6.0 / 6.6 / 11.5 / 11.6 / 13.7 / 16.3 s - the grid could not render until
 * the last of them landed. The cost grows with the plan: a 10,000-row set is ten pages, so
 * ten serial round trips per type.
 *
 * Order is preserved (`Promise.all` resolves positionally), so the merged list is identical
 * to what the serial loop produced - this changes when the rows arrive, never which rows or
 * in what order.
 */
async function fetchEveryPage(
  runId: string,
  type: 'buy' | 'covered' | 'disposition' | 'needs_level',
): Promise<ReorderRecommendation[]> {
  const PAGE = 1000; // endpoint's max `limit`
  const first = await getRecommendations(runId, { pageIndex: 0, pageSize: PAGE, type });
  const pageIndexes: number[] = [];
  for (let page = 1; page < first.pagination.total_pages; page += 1) pageIndexes.push(page);

  const rest = await inFlightAtMost(MAX_CONCURRENT_PAGES, pageIndexes, (page) =>
    getRecommendations(runId, { pageIndex: page, pageSize: PAGE, type }),
  );
  return [...first.data, ...rest.flatMap((p) => p.data)];
}

/**
 * How many pages of ONE type may be in flight at once.
 *
 * Uncapped parallelism is not free on the server side. The four type queries run at the
 * same time, so a ten-page plan would put roughly thirty-six requests on the wire together,
 * and every one of them takes a database session for as long as it runs. The API pool is
 * `pool_size=10, max_overflow=20`, so a single tab opening a single plan could exhaust it
 * and make every other request on the instance queue behind it. Five per type keeps the
 * round trips shallow (which is the whole point of fetching them together) while staying
 * inside what the pool can serve.
 */
const MAX_CONCURRENT_PAGES = 5;

/**
 * Map over `items` with at most `limit` calls running at once, results in input order.
 *
 * A rejection rejects the whole call, exactly as `Promise.all` would: a plan missing one of
 * its pages is not a smaller plan, it is a wrong one, and returning the pages that happened
 * to succeed would quietly under-report the buyer's work.
 */
async function inFlightAtMost<T, R>(
  limit: number,
  items: T[],
  run: (item: T) => Promise<R>,
): Promise<R[]> {
  const out = new Array<R>(items.length);
  let next = 0;
  const worker = async (): Promise<void> => {
    for (;;) {
      const mine = next;
      next += 1;
      if (mine >= items.length) return;
      out[mine] = await run(items[mine]);
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return out;
}

/** What the plans list asks for: one DataGrid page of runs, newest first by default. */
export interface ReorderRunQuery {
  pageIndex: number;
  pageSize: number;
  sorting?: SortingState;
  searchQuery?: string;
}

/**
 * One page of plans (`/scm/reorder`). The endpoint is the existing paginated runs list;
 * `sort`, `dir` and `query` travel through `buildDataGridParams` like every other listing.
 *
 * `query` matches a WAREHOUSE CODE, which is what the search box says: a plan has no other
 * human handle (no UUID surfaces, and a run is identified by its time and its scope).
 */
export async function listReorderRuns(
  query: ReorderRunQuery,
): Promise<ReorderRunHistoryPage> {
  if (USE_M4_MOCKS) {
    return {
      data: [
        {
          run_id: MOCK_RUN_ID,
          status: 'completed',
          buy_scope: 'warehouse',
          warehouse_codes: ['WH-KL'],
          warehouse_count: 1,
          started_at: '2026-07-16T02:15:00',
          finished_at: '2026-07-16T02:15:12',
          summary: MOCK_SUMMARY,
        },
      ],
      pagination: { page: 1, limit: query.pageSize, total: 1, total_pages: 1 },
    };
  }
  const params = buildDataGridParams({
    pageIndex: query.pageIndex,
    pageSize: query.pageSize,
    sorting: query.sorting ?? [],
    searchQuery: query.searchQuery ?? '',
  });
  const res = await apiFetch(`/api/v1/scm/reorder-runs?${params}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the plans'));
  // As in `getTodayRun`: a history run carries its OWN stamped grain, so opening a
  // past run never relabels it with today's policy (AC-F10).
  return (await res.json()) as ReorderRunHistoryPage;
}

// ── M4 cash co-pilot ────────────────────────────────────────────────────────

/** Result of persisting a budget to a run (mirrors PUT .../budget response). */
export interface ApplyBudgetResult {
  run_id: string;
  budget: number;
  funded_count: number;
  deferred_count: number;
  needs_cost_count: number;
  funded_cash: number;
  deferred_cash: number;
}

/**
 * The FULL buy recommendation set for cash ranking/funding - not paginated,
 * because greedy allocation runs across the whole ranked list. `budget` seeds
 * the server-side funding; the slider then recomputes live client-side via
 * `computeFunding` for instant what-if (Phase 2 endpoint A, above).
 */
export async function getBuyRecommendationsForCash(
  runId: string,
): Promise<ReorderRecommendation[]> {
  if (USE_M4_MOCKS) {
    const { funded, deferred, needsCost } = computeFunding(MOCK_BUY_RECS, DEFAULT_BUDGET);
    // Return the union ordered by rank; the view re-splits/annotates itself.
    return [...funded, ...deferred, ...needsCost].sort((a, b) => (a.rank ?? 0) - (b.rank ?? 0));
  }
  // Fetch EVERY buy row (not just the first 1000): the cash slider's ceiling is the
  // Σ of all costed buys, so a truncated set would cap the slider well below the
  // plan's true cash impact. Page past the endpoint's 1000-row limit like the
  // disposition set does.
  return fetchEveryPage(runId, 'buy');
}

/** Every `covered` row for a run: demand the location's own stock already covers.
 *
 *  Fetched whole and separately from the buy set. It is deliberately NOT folded into the
 *  cash co-pilot: a covered row is not a purchase, and letting it into the funding split
 *  would spend budget on something nobody has agreed to buy. */
export async function getCoveredRecommendations(
  runId: string,
): Promise<ReorderRecommendation[]> {
  return fetchEveryPage(runId, 'covered');
}

/** Resolve a covered-by-stock row: keep the stock, or turn it into a purchase.
 *
 *  POST /api/v1/scm/recommendations/{id}/covered-decision  body { choice } */
export async function decideCoveredRow(
  recId: string,
  choice: 'use_stock' | 'buy' | 'pending',
): Promise<{ choice: string; rec_type: string; status: string }> {
  const res = await apiFetch(
    `/api/v1/scm/recommendations/${encodeURIComponent(recId)}/covered-decision`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ choice }),
    },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to record the decision'));
  return res.json();
}

/** One order line behind a planned quantity. */
export interface PlanDemandLine {
  /** The core sales order's own id - never displayed, only powers the link to its record
   *  on the SCM sales-order book (`/scm/sales-orders/{so_id}`, the same target a row of
   *  `SalesOrdersList` itself links to). Optional - absent on a cached response predating
   *  the field, in which case the SO number renders as plain text. */
  so_id?: string | null;
  so_number: string;
  /** The location the ORDER named, or null when it named none. */
  warehouse_code: string | null;
  is_unlocated: boolean;
  order_type: string | null;
  demand_class: string | null;
  order_date: string | null;
  required_date: string | null;
  qty: number;
  /** Who ordered it: the customer name, `Debtor <code>` when the code resolves to
   *  nobody, or `No customer on order` when the order names neither. Never null - the
   *  backend's COALESCE always lands on one of the three. */
  customer_label: string;
  /** Who SOLD it - the salesperson master's `person_label` (or the raw agent code when
   *  nobody has grouped it), resolved off `sales_orders.sales_agent_id`. Null when the
   *  order carries no agent at all - never invented (captain, 21 Aug: "who is the
   *  customer and agent"). Optional - absent on a cached response predating the field. */
  agent_label?: string | null;
  /** The job the units are for - the Project column in both dialogs (F2/F3). Null on an
   *  order with no project behind it, which is a fact about the order. */
  project_title?: string | null;
  /** What they pay for it, when the order line carries a price. */
  unit_price: number | null;
  /**
   * Provenance (captain: "for project is order inquiry, for retail is sales order
   * directly"): which document this line traces back to. `order_inquiry_confirmed` is
   * the CS-confirmed-for-buy leg (`project_need`); a bare `order_inquiry` means the ORDER
   * was created by the Order Inquiry import - it says nothing about whether a row still
   * exists for this line today (`has_inquiry_row` does). Optional - absent on a cached
   * response that predates the field.
   */
  source?: 'sales_order' | 'order_inquiry' | 'order_inquiry_confirmed' | null;
  /**
   * Whether the Order Inquiry worklist actually has a row for this line right now. The
   * `order_inquiry` source above is a stamp on the ORDER, made permanent at creation and
   * never cleared once CS works through every inquiry row off it - a chip built from that
   * alone promises a worklist entry that, most of the time, is no longer there (measured:
   * 605 core orders carry the stamp, 7 still have a row). Optional - absent on a cached
   * response that predates the field; treated as false by the caller in that case.
   */
  has_inquiry_row?: boolean;
  /** How much of an Order Inquiry instruction is already placed on a purchase or shipping
   *  order. `qty` above is what is LEFT of it, so this is what tells a 20 that was always
   *  20 from a 50 that is 30 placed (AC-R8). Only the confirmed project leg carries it -
   *  a retail book line has no instruction to place. */
  linked_qty?: number | null;
}

export interface PlanDemand {
  lines: PlanDemandLine[];
  total: number;
  shown: number;
  committed_total: number;
  unlocated_total: number;
  /** Distinct locations the demand actually sits at - the answer to "why this warehouse". */
  locations: string[];
  /** Which set of locations this list is drawn from: the row's OWN warehouse (the
   *  default), every member of its pool when the plan netted them together, or
   *  (`scope: 'product'` request, 21 Aug) the union across every recommendation this run
   *  wrote for the same product - the set the grouped Buy view's top product-grain row
   *  sums across. */
  scope: 'warehouse' | 'pool' | 'product';
  /** The pool root's code, when the scope is the pool. Null otherwise (including the
   *  product-wide union, which is not one pool). */
  pool_code: string | null;
  /**
   * The channel split of `committed_total` (captain follow-up, 20 Aug). Optional - a
   * cached response taken before this field shipped carries none of the three, so a
   * caller must guard rather than assume they travel together.
   */
  project_total?: number | null;
  retail_total?: number | null;
  unclassified_total?: number | null;
  /**
   * Trailing-window historical order context (captain, 20 Aug follow-up): "for project
   * here, you need to show the past year project order for this item; for retail, the
   * last 3 months, for user to judge whether to top up the quantity ordered." Distinct
   * from `committed_total`/`project_total` above, which are still-OPEN demand - this is
   * the flow of orders PLACED over the window, whatever their status today. Optional for
   * the same cached-response reason as the totals above.
   */
  project_12m_qty?: number | null;
  retail_3m_qty?: number | null;
  project_window_months?: number | null;
  retail_window_months?: number | null;
  demand_context_as_of?: string | null;
  /**
   * The channel this response was narrowed to, echoed back by the backend
   * (`demand_breakdown_service.demand_for_recommendation`'s own `channel` param) - `null`
   * when unfiltered. A cached response predating the field is indistinguishable from
   * `null` here, which is the safe reading: it behaves exactly as an unfiltered request
   * always has.
   */
  channel?: 'project' | 'retail' | 'unclassified' | null;
  /**
   * The trailing-window order-HISTORY section (captain, 21 Aug: "for project, what's the
   * sales order for the past year, who is the customer and agent... for retail, past 3
   * months, same"). Distinct from `lines` above: this is every order PLACED in the
   * window (`project_window_months`/`retail_window_months`, the SAME window
   * `project_12m_qty`/`retail_3m_qty` already total), whatever its status today -
   * delivered orders included, marked via `delivered`. `lines` stays scoped to this
   * row's own location(s) and to still-OPEN demand; this section is the whole product's
   * order flow, matching `project_12m_qty`/`retail_3m_qty`. Empty when the request was
   * not narrowed to `project`/`retail` (unclassified has no configured window), or the
   * window carries nothing. Optional - absent on a cached response predating the field.
   */
  history_lines?: PlanDemandHistoryLine[];
  history_shown?: number;
  /** The UNCAPPED count behind `history_lines` (`history_shown` stays capped) - so a
   *  silent cap on a busy product never reads as "the whole window". */
  history_total?: number;
}

/** One order in the trailing-window history section (see `PlanDemand.history_lines`). */
export interface PlanDemandHistoryLine {
  /** See `PlanDemandLine.so_id` - same purpose, same optionality. */
  so_id?: string | null;
  so_number: string;
  order_date: string | null;
  demand_class: string | null;
  qty: number;
  /** Whether this order has already been delivered in full - the window includes both,
   *  so this is how the popover tells them apart at a glance. */
  delivered: boolean;
  customer_label: string;
  agent_label: string | null;
  /** See `PlanDemandLine.project_title` - the same column on the history tab. */
  project_title?: string | null;
  unit_price: number | null;
}

/** One warehouse's LIVE stock position for a product (captain: "fulfilment planning" style
 *  drill under the grouped Buy view's expand panel). Unlike the frozen `PlanDemand` figures
 *  above, this reads the book as it stands right now - `as_of` says when. All-zero locations
 *  are already dropped server-side, so a location present here has SOMETHING to show.
 *  `available` is signed and never clamped: a negative figure IS the shortfall. */
export interface LocationStockLocation {
  warehouse_id: string;
  /** N-5 (reviewer): backend emits this Optional - a location the extract can't attribute a
   *  code to still comes through as a row, not a dropped one. */
  warehouse_code: string | null;
  on_hand: number;
  reserved: number;
  held_by_decisions: number;
  free: number;
  so_qty: number;
  spo_qty: number;
  available: number;
  /**
   * Whether this location is a SITE POOL rather than a project bin. The On hand lightbox
   * counts pool rows only (R15) - a project bin's stock is already spoken for by an Order
   * Inquiry, so counting it here would double it against the plan's own netting.
   */
  is_pool?: boolean;
  /** Open purchase-order quantity bound for this location. 0 when nothing is on order. */
  po_qty?: number | null;
}

export interface LocationStockResponse {
  product_id: string;
  /** When the stock shown here was last written (R7) - the newest `stock.updated_at` for
   *  the product, NOT the moment the dialog asked. Null when neither that nor a stock
   *  import has ever run. */
  as_of: string | null;
  /** `stock` | `import_job` | `none` - which of the two answers `as_of` is. */
  as_of_source?: 'stock' | 'import_job' | 'none';
  locations: LocationStockLocation[];
}

/** GET /api/v1/scm/reorder-runs/location-stock?product_id=<uuid> - live per-warehouse stock
 *  for one product, fetched on demand (the grouped Buy view's expand panel, per product). */
export async function getLocationStock(productId: string): Promise<LocationStockResponse> {
  const qs = new URLSearchParams({ product_id: productId });
  const res = await apiFetch(`/api/v1/scm/reorder-runs/location-stock?${qs.toString()}`);
  if (!res.ok) {
    throw new Error(await extractApiError(res, 'Failed to load live stock by location'));
  }
  return res.json();
}

/** GET /api/v1/scm/reorder-runs/{run}/recommendations/{rec}/demand?channel=<channel>&scope=product
 *
 *  `channel` narrows the response to ONE of `project`/`retail`/`unclassified` (captain's
 *  own preferred fix, 20 Aug: separate drill icons per channel cell instead of one on
 *  Project carrying everything). Omitted keeps the endpoint's existing unfiltered shape.
 *
 *  `scope: 'product'` (21 Aug follow-up) widens the drill to every recommendation this
 *  run wrote for the SAME product as `recId` - the grouped Buy view's top product-grain
 *  row's own trigger, since that row's channel cells already sum across the product's
 *  whole location set. Omitted keeps the single-row scope every other caller already
 *  gets (the per-location group panel, the ungrouped grid's own row). */
export async function getRecommendationDemand(
  runId: string,
  recId: string,
  channel?: 'project' | 'retail' | 'unclassified',
  scope?: 'product',
): Promise<PlanDemand> {
  const params = new URLSearchParams();
  if (channel) params.set('channel', channel);
  if (scope) params.set('scope', scope);
  const qs = params.toString() ? `?${params.toString()}` : '';
  const res = await apiFetch(
    `/api/v1/scm/reorder-runs/${encodeURIComponent(runId)}/recommendations/${encodeURIComponent(recId)}/demand${qs}`,
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the demand behind this row'));
  return res.json();
}

/** One sales order behind a customer's line in the trend popover. */
export interface CustomerOrderLine {
  so_number: string;
  order_date: string | null;
  qty: number;
  unit_price: number | null;
  warehouse_code: string | null;
}

export interface CustomerOrders {
  lines: CustomerOrderLine[];
  total: number;
  shown: number;
}

/**
 * The sales orders behind one Who-bought-it row.
 *
 * `customerKey` is the customer id, `debtor:<code>` for an order whose debtor code
 * resolves to no customer, or `none` for an order that names neither - the same three
 * cases the label falls back through, so the drill can be opened on every row rather
 * than only on the named ones.
 *
 * GET /api/v1/scm/reorder-runs/{run}/customer-orders
 */
export async function getCustomerOrders(
  runId: string,
  productId: string,
  segment: string,
  customerKey: string,
  limit = 20,
): Promise<CustomerOrders> {
  const qs = new URLSearchParams({
    product_id: productId,
    segment,
    customer_key: customerKey,
    limit: String(limit),
  });
  const res = await apiFetch(
    `/api/v1/scm/reorder-runs/${encodeURIComponent(runId)}/customer-orders?${qs.toString()}`,
  );
  if (!res.ok) {
    throw new Error(await extractApiError(res, 'Failed to load the orders behind this customer'));
  }
  return res.json();
}

/** Persist the chosen budget + funding split to the run ("Apply budget"). */
export async function applyBudget(runId: string, budget: number): Promise<ApplyBudgetResult> {
  if (USE_M4_MOCKS) {
    const { funded, deferred, needsCost, fundedCash, deferredCash } = computeFunding(
      MOCK_BUY_RECS,
      budget,
    );
    return {
      run_id: runId,
      budget,
      funded_count: funded.length,
      deferred_count: deferred.length,
      needs_cost_count: needsCost.length,
      funded_cash: fundedCash,
      deferred_cash: deferredCash,
    };
  }
  const res = await apiFetch(
    `/api/v1/scm/reorder-runs/${encodeURIComponent(runId)}/budget`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ budget }),
    },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to apply budget'));
  return (await res.json()) as ApplyBudgetResult;
}

/** Every `needs_level` row for a run: items the plan could not size because nobody has set
 *  a reorder level for them.
 *
 *  Fetched whole and separately, the same way covered rows are, and for the same reason:
 *  they are not purchases. Omitting them entirely would report "nothing to do" for stock
 *  that has simply never been set up, which is the failure this kind exists to prevent. */
export async function getNeedsLevelRecommendations(
  runId: string,
): Promise<ReorderRecommendation[]> {
  return fetchEveryPage(runId, 'needs_level');
}

/** Take our suggested level as the buyer's own, for one (product, location).
 *
 *  POST /api/v1/scm/reorder-levels/accept-suggestion */
export async function acceptSuggestedLevel(
  productId: string,
  warehouseId: string | null,
): Promise<{ level: number | null; source: string | null }> {
  const res = await apiFetch('/api/v1/scm/reorder-levels/accept-suggestion', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ product_id: productId, warehouse_id: warehouseId }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to accept the suggestion'));
  return res.json();
}

/** Set a reorder level by hand. `null` clears it, which puts the item back in "needs a
 *  level" rather than planning it as zero. */
export async function setReorderLevel(
  productId: string,
  warehouseId: string | null,
  level: number | null,
): Promise<{ level: number | null; source: string | null }> {
  const res = await apiFetch('/api/v1/scm/reorder-levels', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ product_id: productId, warehouse_id: warehouseId, level }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to save the reorder level'));
  return res.json();
}

/**
 * Stock held elsewhere that could cover a shortage instead of buying it.
 *
 * Keyed by product, because the pool is SHARED: two lines for the same product draw on the
 * same units. Fetched once and spent down client-side as decisions are made (see
 * `lib/coverPlan`), which is the only place that knows what has been decided so far.
 *
 * Each source carries its `pool_warehouse_id` and the response carries the run's
 * `cover_scope`, because the map is keyed by PRODUCT while the scope question is per ROW:
 * two rows for the same product can sit in different pools, so the per-row filter has to
 * happen where the row is known (`coverForLine`).
 */
export async function getCoverSources(runId: string): Promise<CoverSourcesResponse> {
  const res = await apiFetch(`/api/v1/scm/reorder-runs/${runId}/cover-sources`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load cover sources'));
  const body = (await res.json()) as {
    sources?: Record<string, CoverSource[]>;
    cover_scope?: CoverScope;
  };
  // An older run payload carries no scope. That reads as `own_pool`, the policy's own
  // default: not knowing what this run is allowed to draw on has to narrow the offer, never
  // open the whole network up.
  return { sources: body.sources ?? {}, cover_scope: body.cover_scope ?? 'own_pool' };
}

export interface CoverSourcesResponse {
  sources: Record<string, CoverSource[]>;
  cover_scope: CoverScope;
}

/**
 * What we last paid each supplier for each item in the plan, and how old that is.
 *
 * Keyed `"{product_id}:{supplier_code}"`. Everything in it comes out of our own purchase
 * ledger - the endpoint makes no claim about what anything is worth today.
 */
/**
 * Is each product's demand sustaining or dying off, per side (S13d).
 *
 * Keyed `"{product_id}:{segment}"`. Verdicts compare the configured window against the
 * one before it AND the same window last year - both, side by side, per the user's call.
 */
export async function getTrajectory(runId: string): Promise<TrajectoryPayload> {
  const res = await apiFetch(`/api/v1/scm/reorder-runs/${runId}/trajectory`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load order trends'));
  return res.json();
}

export async function getLevelSuggestions(runId: string): Promise<LevelSuggestionsPayload> {
  const res = await apiFetch(`/api/v1/scm/reorder-runs/${runId}/level-suggestions`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load level suggestions'));
  const body = (await res.json()) as Partial<LevelSuggestionsPayload>;
  return { suggestions: body.suggestions ?? {}, count: body.count ?? 0 };
}

export async function getProductEconomics(runId: string): Promise<EconomicsPayload> {
  const res = await apiFetch(`/api/v1/scm/reorder-runs/${runId}/product-economics`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load product economics'));
  const body = (await res.json()) as Partial<EconomicsPayload>;
  return {
    products: body.products ?? {},
    count: body.count ?? 0,
    thresholds: body.thresholds ?? { margin_floor_pct: 15, dead_turnover_months: 6 },
    sell_window_months: body.sell_window_months ?? 12,
  };
}

export async function recordLifecycleDecision(input: {
  product_id: string;
  /** null withdraws the decision, back to undecided. */
  decision: 'keep' | 'discontinue' | null;
}): Promise<{ product_id: string; decision: string | null }> {
  const res = await apiFetch('/api/v1/scm/product-lifecycle-decision', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to record the decision'));
  return res.json();
}

export async function getPoBook(
  runId: string,
): Promise<{ po_book: Record<string, PoReceipt[]> }> {
  const res = await apiFetch(`/api/v1/scm/reorder-runs/${runId}/po-book`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the PO book'));
  const body = (await res.json()) as { po_book?: Record<string, PoReceipt[]> };
  return { po_book: body.po_book ?? {} };
}

export async function amendLevelSuggestion(input: {
  product_id: string;
  warehouse_id: string | null;
  /** null withdraws the amendment, back to the engine's figure. */
  amended_level: number | null;
}): Promise<{ suggested_level: number; amended_level: number | null }> {
  const res = await apiFetch('/api/v1/scm/reorder-levels/amend-suggestion', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to amend the level suggestion'));
  return res.json();
}

/**
 * Set (or clear, with `moq: null`) the buyer's own MoQ for one row (20 Aug live test:
 * "MoQ is varying, so we need a place to input it, and when they change it, our
 * calculation should recalculate"). Buy/covered rows only.
 *
 * Backend contract: `PUT /api/v1/scm/recommendations/{rec_id}/moq` body `{moq}` →
 * `{recommendation_id, moq, moq_is_override, master_moq, order_qty, recommended_qty,
 * cash_impact}` - the recalculated figures, so the caller can patch the row in place
 * rather than waiting on a full plan-lines refetch.
 */
export async function setMoqOverride(
  recId: string,
  moq: number | null,
): Promise<{
  recommendation_id: string;
  moq: number | null;
  moq_is_override: boolean;
  master_moq: number | null;
  order_qty: number | null;
  recommended_qty: number | null;
  cash_impact: number | null;
}> {
  const res = await apiFetch(`/api/v1/scm/recommendations/${recId}/moq`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ moq }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to update the MoQ'));
  return res.json();
}

/**
 * Which products on the run have a photo to show: `{product_id: true}` (AC-7).
 *
 * Only the question the icon asks, because the icon is on EVERY row: the answer costs no
 * signature, so a plan of four thousand lines is one cheap call rather than four thousand
 * signed URLs the buyer will never open. The picture itself is `getProductImage` below, on
 * the popover that wants it.
 *
 * A product with nothing to show is ABSENT from the map rather than mapped to false.
 */
export async function getProductImages(
  runId: string,
): Promise<{ has_image: Record<string, boolean> }> {
  const res = await apiFetch(`/api/v1/scm/reorder-runs/${runId}/product-images`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the product photos'));
  const body = (await res.json()) as { has_image?: Record<string, boolean> };
  return { has_image: body.has_image ?? {} };
}

/**
 * The photo of ONE product on the run, signed on the open of its popover (AC-7).
 *
 * `is_primary` says whether anyone ever nominated this picture in Dealer Kit -> Brochure
 * images. The reader falls back to the first catalogue image when nobody has, which is the
 * right thing to show and still worth telling the buyer, so the popover keeps the way back
 * to the picker on screen.
 */
export async function getProductImage(
  runId: string,
  productId: string,
): Promise<{ url: string | null; is_primary: boolean }> {
  const res = await apiFetch(`/api/v1/scm/reorder-runs/${runId}/product-images/${productId}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the product photo'));
  const body = (await res.json()) as { url?: string | null; is_primary?: boolean };
  return { url: body.url ?? null, is_primary: !!body.is_primary };
}

/**
 * The mirror of the order trend, on the buy side: who we bought from, and when (per
 * product, across every supplier - `price-history` narrows to one supplier pair instead).
 */
export async function getPurchaseTrend(runId: string): Promise<PurchaseTrendPayload> {
  const res = await apiFetch(`/api/v1/scm/reorder-runs/${runId}/purchase-trend`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the purchase trend'));
  const body = (await res.json()) as Partial<PurchaseTrendPayload>;
  return { window_months: body.window_months ?? 3, products: body.products ?? {} };
}

export async function getPriceHistory(runId: string): Promise<PriceHistoryPayload> {
  const res = await apiFetch(`/api/v1/scm/reorder-runs/${runId}/price-history`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load price history'));
  const body = (await res.json()) as Partial<PriceHistoryPayload>;
  return {
    stale_after_days: body.stale_after_days ?? 180,
    movement_threshold_pct: body.movement_threshold_pct ?? 5,
    prices: body.prices ?? {},
  };
}
