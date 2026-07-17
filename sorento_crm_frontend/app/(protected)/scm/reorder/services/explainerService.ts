/**
 * ============================================================================
 * SCM M5 Part A — SEMANTIC EXPLANATION / Q&A / MARKET-ADVISORY feature service
 * ============================================================================
 * Layering: hooks (useExplainer) → THIS service → lib/api-client → backend.
 *
 * `USE_M5_MOCKS` (in `lib/explainerMockStore.ts`) toggles the in-memory mocks;
 * shipped false — calls hit the endpoints below, all mounted under
 * `require_module_enabled_with_api_key("scm")` and gated on `scm.dashboard.view`.
 *
 * The M5 layer is a LANGUAGE surface only: it speaks the recommendation's
 * ALREADY-FROZEN numbers (M3/M4) and never recomputes or invents a figure. The
 * server generates lazily and caches, so the explanation for a given rec is
 * built from its frozen inputs exactly once.
 *
 * ── PHASE-2 BACKEND CONTRACT (NEW) ──────────────────────────────────────────
 *
 *  1) Explanation — one plain sentence from the rec's frozen numbers
 *     GET /api/v1/scm/recommendations/{id}/explanation
 *       → 200 { explanation: string }
 *     Lazy-generated the first time it's requested, then CACHED server-side
 *     (keyed by recommendation id) — the frozen inputs never change, so the
 *     sentence is stable. One sentence, no fabricated figures.
 *
 *  2) Ask — a question bounded to THIS recommendation's numbers
 *     POST /api/v1/scm/recommendations/{id}/ask   body { question: string }
 *       → 200 { answer: string }
 *     The answer is grounded strictly in the rec's frozen fields. If the
 *     question needs a number the recommendation does NOT carry, the answer is
 *     EXACTLY "I can't compute that from this recommendation's data." — never a
 *     fabricated figure. (Shared as `REFUSAL` in `lib/explainerMockStore.ts`.)
 *
 *  3) Market advisory — an optional external market signal
 *     GET /api/v1/scm/recommendations/{id}/advisory
 *       → 200 { advisory: string | null }
 *     A short market-research sentence when a signal matches the SKU's category
 *     (e.g. "prices trending +8%; consider ordering sooner"); null when no
 *     signal matches. Advisory is DECISION-SUPPORT prose only — it never changes
 *     the frozen buy quantity.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import {
  USE_M5_MOCKS,
  mockAdvisory,
  mockAsk,
  mockExplanation,
} from '../lib/explainerMockStore';
import type { ReorderRecommendation } from '../types/reorder.types';
import type {
  AdhocSearchResult,
  AdvisoryResult,
  AskResult,
  ExplanationResult,
  MarketProposalResult,
  RunChatResult,
  RunChatTurn,
  RunOverviewResult,
} from '../types/explainer.types';

/** Lazy, cached run-level AI overview — a short brief over the whole run's frozen
 *  aggregates. Real endpoint only (no mock). */
export async function getRunOverview(runId: string): Promise<RunOverviewResult> {
  const res = await apiFetch(
    `/api/v1/scm/reorder-runs/${encodeURIComponent(runId)}/overview`,
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load run overview'));
  return (await res.json()) as RunOverviewResult;
}

/** Grounded, multi-turn plan-chat over the WHOLE run (M6-A). Prior turns are
 *  forwarded so follow-ups resolve; the server reasons over the run's frozen
 *  numbers only. Real endpoint (no mock). */
export async function askRunChat(
  runId: string,
  question: string,
  history: RunChatTurn[],
): Promise<RunChatResult> {
  const res = await apiFetch(
    `/api/v1/scm/reorder-runs/${encodeURIComponent(runId)}/chat`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, history }),
    },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to answer question'));
  return (await res.json()) as RunChatResult;
}

/** Ad-hoc market web search fired from the planning flow (M6-B). Caches signals
 *  that then drive the per-rec advisory + feed the plan-chat. Real endpoint. */
export async function searchMarket(
  query: string,
  categoryRef?: string | null,
  currency?: string | null,
): Promise<AdhocSearchResult> {
  const res = await apiFetch('/api/v1/scm/market-search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, category_ref: categoryRef ?? null, currency: currency ?? null }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Market search failed'));
  return (await res.json()) as AdhocSearchResult;
}

/** Map a market signal → per-line qty-uplift PROPOSAL on the run's matching buy
 *  recs (M8-E5). Writes nothing; the user confirms each line via /adjust. */
export async function getMarketProposal(
  runId: string,
  opts: { signalId?: string | null; query?: string | null; categoryRef?: string | null },
): Promise<MarketProposalResult> {
  const res = await apiFetch(
    `/api/v1/scm/reorder-runs/${encodeURIComponent(runId)}/market-proposal`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        signal_id: opts.signalId ?? null,
        query: opts.query ?? null,
        category_ref: opts.categoryRef ?? null,
      }),
    },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Market proposal failed'));
  return (await res.json()) as MarketProposalResult;
}

/** Lazy, cached one-sentence explanation for a recommendation (M5-A1). */
export async function getRecommendationExplanation(
  rec: ReorderRecommendation,
): Promise<ExplanationResult> {
  if (USE_M5_MOCKS) return { explanation: mockExplanation(rec) };
  const res = await apiFetch(
    `/api/v1/scm/recommendations/${encodeURIComponent(rec.id)}/explanation`,
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load explanation'));
  return (await res.json()) as ExplanationResult;
}

/** Ask a question bounded to the recommendation's frozen numbers (M5-A2). */
export async function askRecommendation(
  rec: ReorderRecommendation,
  question: string,
): Promise<AskResult> {
  if (USE_M5_MOCKS) return { answer: mockAsk(rec, question) };
  const res = await apiFetch(
    `/api/v1/scm/recommendations/${encodeURIComponent(rec.id)}/ask`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to answer question'));
  return (await res.json()) as AskResult;
}

/** Optional market advisory for a recommendation — null when no signal (M5-A3). */
export async function getRecommendationAdvisory(
  rec: ReorderRecommendation,
): Promise<AdvisoryResult> {
  if (USE_M5_MOCKS) return { advisory: mockAdvisory(rec) };
  const res = await apiFetch(
    `/api/v1/scm/recommendations/${encodeURIComponent(rec.id)}/advisory`,
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load market advisory'));
  return (await res.json()) as AdvisoryResult;
}
