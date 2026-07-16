/**
 * ============================================================================
 * SCM M4 — Cash co-pilot CLIENT-SIDE allocator (production, not a mock)
 * ============================================================================
 * The budget slider recomputes funded/deferred LIVE client-side against each
 * rec's FROZEN `rank_score` (M4-D3) — no per-tick round-trip. The server owns the
 * authoritative funding: it computes the same greedy split for `GET
 * ?budget=X` and PERSISTS it on `PUT /budget` ("Apply budget"). This module is
 * the deterministic allocator both the slider and the initial render use; it is
 * intentionally pure (no network / Date / random) so it matches the backend
 * `cash_ranking.allocate_funding` byte-for-byte and is unit-testable.
 * ============================================================================
 */
import type { RankFactor, ReorderRecommendation } from '../types/reorder.types';

/** Slider granularity (RM). */
export const BUDGET_STEP = 500;

/** Graceful-degrade score (M4-D14): Σ(wᵢ·vᵢ) / Σ(wᵢ present). Dropped factors
 *  (present:false) never enter either sum, so an uncosted SKU's missing margin
 *  doesn't dilute the score. Mirrors backend `cash_ranking.rank_score`. */
export function scoreFromFactors(factors: RankFactor[]): number {
  let num = 0;
  let den = 0;
  for (const f of factors) {
    if (!f.present || f.value === null) continue;
    num += f.weight * f.value;
    den += f.weight;
  }
  return den === 0 ? 0 : num / den;
}

/** Result of allocating a budget across ranked recs. */
export interface FundingResult {
  /** Costed recs the budget funds, each annotated `funding_status:'funded'`. */
  funded: ReorderRecommendation[];
  /** Costed recs the budget skips, annotated `funding_status:'deferred'`. */
  deferred: ReorderRecommendation[];
  /** Uncosted recs (M4-D16) — un-rankable by cash, `funding_status:'needs_cost'`;
   *  they never fund/defer or touch the budget. */
  needsCost: ReorderRecommendation[];
  /** Σ cash_impact of funded costed recs (≤ budget). */
  fundedCash: number;
  /** Σ cash_impact of deferred costed recs. */
  deferredCash: number;
  /** budget − fundedCash. */
  remaining: number;
}

/**
 * Deterministic greedy allocation (M4-D3 + M4-D16). Split buys COSTED vs
 * UNCOSTED: an uncosted buy (cash_impact null) CANNOT be cash-ranked, so it goes
 * to the `needsCost` bucket untouched — it never funds/defers or draws from the
 * budget. Over the COSTED buys only, walk by rank ascending and fund a buy only
 * if its whole cash_impact fits the remaining budget, else SKIP it and continue
 * to the next that fits (MoQ = all-or-nothing). Budget 0 → all costed deferred.
 * Σ funded cash ≤ budget. Matches the backend allocator exactly.
 */
export function computeFunding(
  recs: ReorderRecommendation[],
  budget: number,
): FundingResult {
  const ordered = [...recs].sort((a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity));
  const funded: ReorderRecommendation[] = [];
  const deferred: ReorderRecommendation[] = [];
  const needsCost: ReorderRecommendation[] = [];
  let remaining = budget;
  let fundedCash = 0;
  let deferredCash = 0;

  for (const rec of ordered) {
    const cost = rec.cash_impact;
    // Uncosted — un-rankable by cash; parked in the "Needs cost" bucket.
    if (cost === null) {
      needsCost.push({ ...rec, funding_status: 'needs_cost' });
      continue;
    }
    if (budget > 0 && cost <= remaining) {
      remaining -= cost;
      fundedCash += cost;
      funded.push({ ...rec, funding_status: 'funded' });
    } else {
      deferredCash += cost; // overflow (or budget 0) — skip and continue
      deferred.push({ ...rec, funding_status: 'deferred' });
    }
  }

  // Deferred shown by soonest stockout first — the highest risk of NOT funding.
  deferred.sort(
    (a, b) => (a.days_to_stockout ?? Infinity) - (b.days_to_stockout ?? Infinity),
  );

  return { funded, deferred, needsCost, fundedCash, deferredCash, remaining: budget - fundedCash };
}

/** Σ cash_impact across the COSTED buy recs (uncosted contribute 0). */
export function totalCostedCash(recs: ReorderRecommendation[]): number {
  return recs.reduce((s, r) => s + (r.cash_impact ?? 0), 0);
}

/** Slider ceiling — Σ costed cash with ~10% headroom, rounded up to RM 1,000.
 *  Falls back to one step when the run has no costed cash (all uncosted). */
export function sliderMaxFor(recs: ReorderRecommendation[]): number {
  const total = totalCostedCash(recs);
  if (total <= 0) return BUDGET_STEP;
  return Math.ceil((total * 1.1) / 1_000) * 1_000;
}

/** Default budget — ~60% of the costed total, rounded to a step, so the funded
 *  boundary lands mid-list with a visible funded/deferred split on first render. */
export function defaultBudgetFor(recs: ReorderRecommendation[]): number {
  const total = totalCostedCash(recs);
  if (total <= 0) return 0;
  return Math.max(BUDGET_STEP, Math.round((total * 0.6) / BUDGET_STEP) * BUDGET_STEP);
}
