/**
 * ============================================================================
 * SCM M4 - Cash co-pilot CLIENT-SIDE allocator (production, not a mock)
 * ============================================================================
 * The budget slider recomputes funded/deferred LIVE client-side against each
 * rec's FROZEN `rank_score` (M4-D3) - no per-tick round-trip. The server owns the
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
  /** Uncosted recs (M4-D16) - un-rankable by cash, `funding_status:'needs_cost'`;
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
 * to the `needsCost` bucket untouched - it never funds/defers or draws from the
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
    // Uncosted - un-rankable by cash; parked in the "Needs cost" bucket.
    if (cost === null) {
      needsCost.push({ ...rec, funding_status: 'needs_cost' });
      continue;
    }
    if (budget > 0 && cost <= remaining) {
      remaining -= cost;
      fundedCash += cost;
      funded.push({ ...rec, funding_status: 'funded' });
    } else {
      deferredCash += cost; // overflow (or budget 0) - skip and continue
      deferred.push({ ...rec, funding_status: 'deferred' });
    }
  }

  // Deferred shown by soonest stockout first - the highest risk of NOT funding.
  deferred.sort(
    (a, b) => (a.days_to_stockout ?? Infinity) - (b.days_to_stockout ?? Infinity),
  );

  // Clean 1..N priority per section (M4 slice-B UX) - the raw global rank (e.g.
  // 205) confuses; the user wants a sequential position in each list. Assigned
  // AFTER each section's final sort so the number matches the displayed order.
  funded.forEach((r, i) => (r.display_rank = i + 1));
  deferred.forEach((r, i) => (r.display_rank = i + 1));
  needsCost.forEach((r, i) => (r.display_rank = i + 1));

  return { funded, deferred, needsCost, fundedCash, deferredCash, remaining: budget - fundedCash };
}

/** Σ cash_impact across the COSTED buy recs (uncosted contribute 0). */
export function totalCostedCash(recs: ReorderRecommendation[]): number {
  return recs.reduce((s, r) => s + (r.cash_impact ?? 0), 0);
}

// ---------------------------------------------------------------------------
// M8 - pin-aware budget split (slice C). Same greedy-by-rank allocator, but
// with a manual-override layer on top: PINNED rows (drag-to-fund) are
// force-funded and consume budget FIRST (a pin never drops to Over budget on a
// budget decrease - the free figure just goes negative to reflect the
// overspend); REJECTED rows stay in their natural budget section (M8-F1: reject
// never moves a row between sections) but their cash is EXCLUDED from committed
// since a rejected line won't be bought; only the remaining un-pinned rows
// reshuffle by rank until the budget is spent. Uncosted rows (unit_cost null)
// can't be budgeted and are parked in `needsCost` for the banner. Pure (no
// network / Date / random).
// ---------------------------------------------------------------------------

/** Minimal row shape the M8 split needs - decoupled from the heavy rec type so
 *  the prototype mock (and the Phase-2 payload) can drive it directly. */
export interface M8FundingRow {
  id: string;
  rank: number;
  order_qty: number;
  unit_cost: number | null;
}

export interface M8FundingResult<T extends M8FundingRow> {
  /** Rows funded within budget (pins first, then greedy by rank). */
  within: T[];
  /** Costed rows the budget skips. */
  over: T[];
  /** Uncosted rows - excluded from the budget entirely (banner only). */
  needsCost: T[];
  /** Σ cash of the within-budget rows. */
  committed: number;
  /** budget - committed (can be negative when pins overspend). */
  free: number;
}

/** Cash impact of a row = live qty x unit cost (null when uncosted). */
export function m8RowCash(row: M8FundingRow): number | null {
  if (row.unit_cost === null) return null;
  return row.order_qty * row.unit_cost;
}

/** Manual-override sets that sit on top of the greedy budget split. */
export interface M8Overrides {
  /** Force-funded (pinned) rows - within budget first, never defer on a cut. */
  pins: ReadonlySet<string>;
  /** Rejected rows - kept in their natural budget section (M8-F1), but their
   *  cash is excluded from committed since a rejected line won't be bought. */
  rejects: ReadonlySet<string>;
  /** Manually deferred rows (dragged down) - forced to Over budget unless pinned. */
  forcedOver?: ReadonlySet<string>;
}

/**
 * Pin-aware greedy split (M8-C2, M8-C3, M8-C4, M8-F1). Pinned rows fund first and
 * consume budget first (and stay within even on overspend); manually-deferred
 * rows are forced to Over; the remaining un-pinned costed rows fund greedily by
 * rank while they fit; the rest defer. REJECTED rows are NOT routed to a separate
 * bucket - they flow to their normal pin/budget/drag placement so a reject never
 * moves a row between sections; their cash is simply excluded from `committed`
 * (they won't be bought, so they don't draw down the budget).
 */
export function computeFundingM8<T extends M8FundingRow>(
  rows: T[],
  budget: number,
  overrides: M8Overrides,
): M8FundingResult<T> {
  const { pins, rejects, forcedOver } = overrides;
  const within: T[] = [];
  const over: T[] = [];
  const needsCost: T[] = [];
  let committed = 0;

  // Uncosted -> needs-cost bucket, untouched by the budget.
  const costed = rows.filter((r) => {
    if (r.unit_cost === null) {
      needsCost.push(r);
      return false;
    }
    return true;
  });

  const byRank = [...costed].sort((a, b) => a.rank - b.rank);

  // Pins are ADDITIVE, not budget-first: a dragged-up (pinned) row is force-funded
  // WITHOUT reducing the budget the greedy has for the OTHER rows, so pinning one line
  // never evicts an already-funded line (the overspend just shows as negative free).
  // The greedy then fills the budget over the remaining un-pinned, un-deferred rows.
  let remaining = budget;
  for (const row of byRank) {
    if (forcedOver?.has(row.id)) {
      over.push(row); // manually dragged to Over - stays out regardless of budget
      continue;
    }
    if (pins.has(row.id)) {
      within.push(row); // force-funded, does not draw down `remaining`
      continue;
    }
    const cost = m8RowCash(row) ?? 0;
    // Same 1e-9 float tolerance the backend allocator applies so the boundary line
    // funds identically on client and persisted server split.
    if (budget > 0 && cost <= remaining + 1e-9) {
      within.push(row);
      remaining -= cost;
    } else {
      over.push(row);
    }
  }

  // committed = cash of every Within row that is NOT rejected (a rejected line stays in
  // its section but is not bought, so it does not spend budget).
  for (const row of within) {
    if (!rejects.has(row.id)) committed += m8RowCash(row) ?? 0;
  }

  // Keep each section ordered by rank for a stable, legible table.
  within.sort((a, b) => a.rank - b.rank);
  over.sort((a, b) => a.rank - b.rank);

  return { within, over, needsCost, committed, free: budget - committed };
}

/** Slider ceiling - Σ costed cash with ~10% headroom, rounded up to RM 1,000.
 *  Falls back to one step when the run has no costed cash (all uncosted). */
export function sliderMaxFor(recs: ReorderRecommendation[]): number {
  const total = totalCostedCash(recs);
  if (total <= 0) return BUDGET_STEP;
  return Math.ceil((total * 1.1) / 1_000) * 1_000;
}

/**
 * The budget the plan opens with.
 *
 * The COMPANY's figure when one is configured (`scm.purchasing_budget`, served by
 * `/scm/config/cash-budget`). Otherwise the plan's own costed total, so nothing is deferred
 * for a reason nobody gave.
 *
 * It used to open at ~60% of the plan's cost, to put a visible cut line mid-list. That
 * teaches the mechanic at the price of inventing a constraint: a RM 5.9m plan opened with
 * RM 3.55m "available" and 59 lines under a heading reading Over budget, which is a number
 * the company never stated presented as if it had. A limit nobody set is not a cautious
 * default, it is a wrong one - so the plan now shows itself whole and the buyer types the
 * limit they actually have.
 */
export function defaultBudgetFor(
  recs: ReorderRecommendation[],
  configuredBudget?: number | null,
): number {
  if (configuredBudget != null && configuredBudget > 0) return configuredBudget;
  const total = totalCostedCash(recs);
  if (total <= 0) return 0;
  return Math.ceil(total / BUDGET_STEP) * BUDGET_STEP;
}
