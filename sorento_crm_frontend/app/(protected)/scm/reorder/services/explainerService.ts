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
  AdvisoryResult,
  AskResult,
  ExplanationResult,
} from '../types/explainer.types';

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
