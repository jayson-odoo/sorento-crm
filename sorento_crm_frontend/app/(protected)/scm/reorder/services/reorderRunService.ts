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
import type { CoverSource } from '../lib/coverPlan';
import type { PriceHistoryPayload } from '../lib/priceAdvice';
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
  warehouse_codes: string[];
  warehouse_count: number;
  /** Naive-UTC ISO strings - format with `formatDateTimeInMalaysia` (raw string). */
  started_at: string | null;
  finished_at: string | null;
  /** Populated once the run completed; null while running / failed. */
  summary: ReorderRunSummary | null;
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
}

const DEFAULT_STAGE: ReorderRunStage = 'resolving_policies';

/** Launch a run. Returns a running run record the hook then polls. */
export async function createReorderRun(req: CreateReorderRunRequest): Promise<ReorderRun> {
  if (USE_M4_MOCKS) return mockRun(); // completes instantly - mock has no worker
  const res = await apiFetch('/api/v1/scm/reorder-runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      warehouse_codes: req.warehouse_codes,
      budget_id: req.budget_id ?? null,
      include_market: req.include_market ?? false,
      // Product scope (AC-B8a) is sent ONLY when the user narrowed the run. Empty
      // means every product, and omitting the key keeps the request byte-identical
      // to what the backend accepts today, so adding the picker cannot change an
      // unnarrowed run.
      ...(req.product_codes?.length ? { product_codes: req.product_codes } : {}),
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
  };
}

/** DEMO / ADMIN reset - roll a run's decisions back to as-generated (clears every
 *  accept/reject/adjust + the draft POs they staged) so the flow can be re-demoed.
 *  Confirmed (active) POs are untouched. Returns what was cleared. */
export async function resetRunDecisions(
  runId: string,
): Promise<{ run_id: string; decisions_cleared: number; overrides_cleared: number }> {
  const res = await apiFetch(
    `/api/v1/scm/reorder-runs/${encodeURIComponent(runId)}/reset-decisions`,
    { method: 'POST' },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to reset the plan'));
  return res.json();
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
  const PAGE = 1000; // endpoint's max `limit`
  const first = await getRecommendations(runId, {
    pageIndex: 0,
    pageSize: PAGE,
    type: 'disposition',
  });
  const out = [...first.data];
  for (let page = 1; page < first.pagination.total_pages; page += 1) {
    const next = await getRecommendations(runId, {
      pageIndex: page,
      pageSize: PAGE,
      type: 'disposition',
    });
    out.push(...next.data);
  }
  return out;
}

/** Newest-first paginated run history (drives the Run history panel). */
export async function listReorderRuns(
  page: number,
  limit: number,
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
      pagination: { page: 1, limit, total: 1, total_pages: 1 },
    };
  }
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
  const PAGE = 1000; // endpoint's max `limit`
  const first = await getRecommendations(runId, { pageIndex: 0, pageSize: PAGE, type: 'buy' });
  const out = [...first.data];
  for (let page = 1; page < first.pagination.total_pages; page += 1) {
    const next = await getRecommendations(runId, { pageIndex: page, pageSize: PAGE, type: 'buy' });
    out.push(...next.data);
  }
  return out;
}

/** Every `covered` row for a run: demand the location's own stock already covers.
 *
 *  Fetched whole and separately from the buy set. It is deliberately NOT folded into the
 *  cash co-pilot: a covered row is not a purchase, and letting it into the funding split
 *  would spend budget on something nobody has agreed to buy. */
export async function getCoveredRecommendations(
  runId: string,
): Promise<ReorderRecommendation[]> {
  const PAGE = 1000;
  const first = await getRecommendations(runId, { pageIndex: 0, pageSize: PAGE, type: 'covered' });
  const out = [...first.data];
  for (let page = 1; page < first.pagination.total_pages; page += 1) {
    const next = await getRecommendations(runId, { pageIndex: page, pageSize: PAGE, type: 'covered' });
    out.push(...next.data);
  }
  return out;
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
  so_number: string;
  /** The location the ORDER named, or null when it named none. */
  warehouse_code: string | null;
  is_unlocated: boolean;
  order_type: string | null;
  demand_class: string | null;
  order_date: string | null;
  required_date: string | null;
  qty: number;
}

export interface PlanDemand {
  lines: PlanDemandLine[];
  total: number;
  shown: number;
  committed_total: number;
  unlocated_total: number;
  /** Distinct locations the demand actually sits at - the answer to "why this warehouse". */
  locations: string[];
}

/** GET /api/v1/scm/reorder-runs/{run}/recommendations/{rec}/demand */
export async function getRecommendationDemand(
  runId: string,
  recId: string,
): Promise<PlanDemand> {
  const res = await apiFetch(
    `/api/v1/scm/reorder-runs/${encodeURIComponent(runId)}/recommendations/${encodeURIComponent(recId)}/demand`,
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the demand behind this row'));
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
  const PAGE = 1000;
  const first = await getRecommendations(runId, {
    pageIndex: 0,
    pageSize: PAGE,
    type: 'needs_level',
  });
  const out = [...first.data];
  for (let page = 1; page < first.pagination.total_pages; page += 1) {
    const next = await getRecommendations(runId, {
      pageIndex: page,
      pageSize: PAGE,
      type: 'needs_level',
    });
    out.push(...next.data);
  }
  return out;
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
 */
export async function getCoverSources(
  runId: string,
): Promise<Record<string, CoverSource[]>> {
  const res = await apiFetch(`/api/v1/scm/reorder-runs/${runId}/cover-sources`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load cover sources'));
  const body = (await res.json()) as { sources?: Record<string, CoverSource[]> };
  return body.sources ?? {};
}

/**
 * What we last paid each supplier for each item in the plan, and how old that is.
 *
 * Keyed `"{product_id}:{supplier_code}"`. Everything in it comes out of our own purchase
 * ledger - the endpoint makes no claim about what anything is worth today.
 */
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
