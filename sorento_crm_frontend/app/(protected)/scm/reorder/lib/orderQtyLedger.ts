/**
 * The order-qty ledger's pure math (S3, UAC B).
 *
 * The ledger popover reads the SAME composition state the Decision cell and the Adjust
 * dialog use (`coverForLine` / `poOffset`, S16) rather than forking a second model of what
 * a line's buy is made of. This file adds only the two pieces the ledger itself introduces
 * on top of that state:
 *
 * - which cover parts are "on" right now, and what is left to buy once they are toggled;
 * - the optional forecast add-on, and replaying the ALREADY-agreed MOQ/order-multiple
 *     rounding formula (`reorder_engine.round_order_qty`) against whatever that live number
 *     comes out to.
 *
 * Nothing here recomputes what the engine froze at run time (safety stock, ROP, order-up-to,
 * the frozen `order_qty` itself) - those stay exactly as run (UAC non-goal: never change the
 * engine's qty math). This only replays a rounding RULE that already exists, against a
 * number that only exists because the buyer is looking at the ledger live.
 */
import type { CoverProposal } from './coverPlan';
import { poOffset } from './poCover';
import { trendAdvice, type TrajectoryEntry } from './trajectory';

/**
 * Floor at MOQ, then round UP to the nearest order multiple - mirrors
 * `reorder_engine.round_order_qty` BYTE-FOR-BYTE (fix-cluster, 2026-08-12), so the ledger
 * never invents its own rounding rule or drifts from it at an edge:
 *
 *   def round_order_qty(qty, moq, order_multiple):
 *       q = float(qty)
 *       if moq is not None and q < float(moq):
 *           q = float(moq)
 *       if order_multiple and float(order_multiple) > 0:
 *           q = math.ceil(q / order_multiple) * order_multiple
 *       return float(q)
 *
 * Two edges an earlier version of this function got wrong by adding safety the backend
 * does not have:
 *
 * - the MOQ floor applies whenever MOQ is SET (`moq is not None`), never gated on
 *     `moq > 0` - a `moq` of 0 is a real (if odd) config value, and the backend floors
 *     against it exactly the same as any other. `qty` is never clamped to zero first
 *     either: a `qty` of 0 with a positive MOQ configured floors UP to that MOQ on the
 *     backend, it does not short-circuit to 0 ("nothing to buy" is the CALLER's job to
 *     recognise before this ever runs, exactly as `reorder_engine.order_qty` does - see
 *     its own `if recommended <= 0: return 0.0, 0.0` guard BEFORE calling this).
 * - the order-multiple condition is unchanged (`orderMultiple != null && orderMultiple
 *     > 0`), matching Python's `order_multiple and order_multiple > 0` (falsy on 0/None).
 */
export function roundOrderQty(
  qty: number,
  moq: number | null | undefined,
  orderMultiple: number | null | undefined,
): number {
  let q = qty;
  if (moq != null && q < moq) q = moq;
  if (orderMultiple != null && orderMultiple > 0) {
    q = Math.ceil(q / orderMultiple) * orderMultiple;
  }
  return q;
}

/** The two rounding rules a line carries, as they sit on `PlanLine.order_qty_inputs`. */
export interface OrderQtyRounding {
  moq: number | null;
  order_multiple: number | null;
}

/**
 * "Nd label", or `null` when the day count itself is absent (21 Aug fix).
 *
 * The ledger used to glue `fmtInt(null)` (the em-dash, `-`) straight onto the unit -
 * `-d review`, `-d lead` - which reads as a formatting bug, not as "no review period is
 * configured for this policy". The caller renders a real sentence in that case instead
 * (see `AutoDerivation`); this only ever returns a term worth showing.
 */
export function daysTerm(days: number | null | undefined, label: string): string | null {
  if (days == null) return null;
  return `${Math.round(days)}d ${label}`;
}

/**
 * The rounding a RECORDED buy goes through, wherever the buyer typed it.
 *
 * The ledger replayed `roundOrderQty` and the two other controls did not, so accepting a
 * suggestion (`Buy 14`) and reaching the same mixture through the ledger (`Buy 20`) recorded
 * different, and in one case illegal, orders for the same row. Every surface that turns a
 * number into a `PlanDecision.buy` calls THIS, so a decision can never carry a quantity the
 * supplier would refuse.
 *
 * Nothing to buy stays nothing: a positive MoQ against a zero remainder would otherwise
 * invent an order for a row the buyer just covered outright. That is the same guard
 * `reorder_engine.order_qty` applies before it rounds (`if recommended <= 0: return 0.0`),
 * which is why `roundOrderQty` itself does not carry it.
 */
export function roundBuyQty(qty: number, rounding: OrderQtyRounding): number {
  if (!(qty > 0)) return 0;
  return roundOrderQty(qty, rounding.moq, rounding.order_multiple);
}

export interface MixtureResult {
  /** Units drawn from the cover pool right now (0 when the stock toggle is off). */
  stockQty: number;
  /** Units the open PO book absorbs right now (0 when the PO toggle is off). */
  usePo: number;
  /** What is left to buy once the two above are applied. */
  buy: number;
}

/**
 * Recompute the buy after toggling which cover parts are in play.
 *
 * `needed` is the same base every other cover surface on the row uses - `Math.ceil(order_qty)`
 * (see `PlanLineDecisionCell`) - so a toggle here can never disagree with the Decision cell or
 * the Suggested-action column reading the same line.
 */
export function composeMixture(
  needed: number,
  cover: CoverProposal,
  poQty: number,
  toggles: { stockOn: boolean; poOn: boolean; stockQty?: number },
): MixtureResult {
  const stockOn = toggles.stockOn && cover.coverQty > 0;
  // The buyer's own per-location figures when they have edited them, the proposal's own
  // total otherwise. The gap the two are measured against is the proposal's whole shortage
  // (`coverQty + buyQty`), which is what makes an edited cover fall straight through into
  // the buy: cover less, buy more, and never a negative order.
  const proposed = cover.coverQty;
  const stockQty = stockOn ? (toggles.stockQty ?? proposed) : 0;
  const gap = cover.coverQty + cover.buyQty;
  const afterStock = stockOn ? Math.max(0, gap - stockQty) : needed;
  const { usePo, buy } = poOffset(afterStock, toggles.poOn ? poQty : 0);
  return { stockQty, usePo, buy };
}

/** Matches `scm.reorder_policy.level_cover_months`'s column default (migration 273_scm_
 *  module_schema). Used only as a fallback when a row's own `suggestion_basis` never ran
 *  (no movement history yet) - the live policy value is not threaded onto the frozen row. */
const DEFAULT_LEVEL_COVER_MONTHS = 2;

/** Days in a month, for turning a cover-months horizon into the "next Xd" the ledger states -
 *  matches how `suggest_level`'s own `cover_months` is a month count, not a day count. */
const DAYS_PER_MONTH = 30;

/** Named per mode, so the "+ Add" label can say WHERE its horizon came from rather than
 *  leaving the buyer to trust a bare day count (user feedback: "the label must name its
 *  source"). */
const FORECAST_SOURCE_LABEL = {
  manual: 'cover window per policy',
  auto: 'review period per policy',
} as const;

export interface ForecastAddOn {
  /**
   * The number the "+ Add" action proposes. Never applied by default (UAC B5).
   *
   * Starts as round(rate x horizon), then follows the SAME trajectory verdict that drives
   * the row's own Trend pill (`trendAdvice`): rising bumps it up, falling scales it down
   * (floored at 0 - a flat proposal on a dying line is the bug this replaces: "declining
   * trend also suggests +360 same as rising"). Holding/quiet/no_history leave it flat,
   * because those verdicts say nothing about buying more or less either.
   */
  qty: number;
  horizonDays: number;
  ratePerDay: number;
  /** Where `horizonDays` comes from - appended to the label, never left silent. */
  sourceLabel: string;
  /** "orders rising +33%" / "orders falling -80%" - null on holding/quiet/no_history/no
   *  trend data, where `qty` is the flat proposal untouched. */
  trendNote: string | null;
}

/**
 * The optional forecast add-on THE BUY block may offer.
 *
 * Auto mode uses the policy's own review window (`rec.review_days`, the same window the
 * order-up-to derivation already folds in). Manual mode has no review window - the level
 * basis exists specifically because a forecast term is not part of its trigger - so it
 * borrows the level suggestion's own cover-months horizon instead, converted to days.
 *
 * `qty` can come back `0` (a falling trend that ate the whole flat proposal) - that is
 * DIFFERENT from returning `null` (no measurable demand at all, so there is nothing to
 * offer in the first place): the caller renders a disabled explanatory line for the
 * former and nothing at all for the latter.
 */
export function forecastAddOn(
  rec: {
    policy_type?: string | null;
    forecast_daily_demand?: number | null;
    review_days?: number | null;
    suggestion_basis?: { cover_months?: number } | null;
  },
  trend?: TrajectoryEntry,
): ForecastAddOn | null {
  const rate = rec.forecast_daily_demand;
  if (rate == null || rate <= 0) return null;
  const manual = rec.policy_type === 'reorder_level';
  const horizonDays = manual
    ? Math.round((rec.suggestion_basis?.cover_months ?? DEFAULT_LEVEL_COVER_MONTHS) * DAYS_PER_MONTH)
    : Math.round(rec.review_days ?? 0);
  if (!(horizonDays > 0)) return null;
  const flatQty = Math.round(rate * horizonDays);
  if (flatQty <= 0) return null;

  const advice = trendAdvice(trend, flatQty);
  let qty = flatQty;
  let trendNote: string | null = null;
  if (advice?.direction === 'more') {
    qty = flatQty + advice.delta;
    trendNote = `orders rising +${advice.pct}%`;
  } else if (advice?.direction === 'less') {
    // The SAME %-of-buy math `trendAdvice` already uses for the row's own advisory,
    // replayed against the flat add-on rather than the buy qty - "reduce proportionally,
    // floor 0" (advice.delta is already floored and capped at flatQty).
    qty = Math.max(0, flatQty - advice.delta);
    trendNote = `orders falling -${advice.pct}%`;
  }

  return {
    qty,
    horizonDays,
    ratePerDay: rate,
    sourceLabel: manual ? FORECAST_SOURCE_LABEL.manual : FORECAST_SOURCE_LABEL.auto,
    trendNote,
  };
}

export interface LevelLine {
  level: number | null;
  sourceLabel: string;
  /** Not yet emitted by the backend (no `reorder_level_set_at` on the frozen row) - renders
   *  only when a caller passes one, per UAC B2's "set date if available". */
  setAt: string | null;
}

const LEVEL_SOURCE_LABEL: Record<string, string> = {
  manual: 'buyer set',
  accepted_suggestion: 'buyer accepted the suggestion',
};

/** THE LINE, manual mode: the level a buyer owns, its source, and (when the backend ever
 *  carries it) when it was set. Mirrors the same buyer-level-then-master fallback the
 *  "Reorder level" column and `PlanChecklistPopover` already use. */
export function levelLine(rec: {
  reorder_level?: number | null;
  reorder_level_source?: string | null;
  reorder_level_set_at?: string | null;
  master_reorder_level?: number | null;
}): LevelLine {
  if (rec.reorder_level != null) {
    return {
      level: rec.reorder_level,
      sourceLabel: LEVEL_SOURCE_LABEL[rec.reorder_level_source ?? ''] ?? 'buyer level',
      setAt: rec.reorder_level_set_at ?? null,
    };
  }
  if (rec.master_reorder_level != null) {
    return {
      level: rec.master_reorder_level,
      sourceLabel: 'AutoCount master (no buyer level set)',
      setAt: null,
    };
  }
  return { level: null, sourceLabel: 'not set', setAt: null };
}

/**
 * Whether THE LINE is actually breached, computed honestly off `net` vs its own basis -
 * never trusted off `rec_type` alone.
 *
 * A `covered` row can still sit ABOVE its line (net > level/ROP): the "Gap to line" figure
 * on that row is not a shortfall, it is the engine's own covered committed demand, and
 * showing it under a "Gap to line" label reads as a bug ("net 135, level 120, gap 15?").
 * A `covered` row can ALSO sit at-or-below its line and still be covered - the pool-cover
 * case, where cross-warehouse stock closes a real gap - and that real gap has to keep
 * reading as a gap, with the cover block explaining how it gets closed.
 *
 * `basisValue: null` (no level and no reorder point on file) reads as breached: there is
 * nothing honest to compare `net` against, so this falls back to the old, always-shown
 * "Gap to line" row rather than asserting a line-status sentence it cannot support.
 */
export interface LineBreachStatus {
  breached: boolean;
  /** "level" (manual mode) or "reorder point" (auto mode) - null when neither is on file. */
  basisLabel: 'level' | 'reorder point' | null;
  basisValue: number | null;
}

export function lineBreachStatus(
  rec: {
    policy_type?: string | null;
    reorder_point?: number | null;
    reorder_level?: number | null;
    master_reorder_level?: number | null;
  },
  net: number | null,
): LineBreachStatus {
  const manual = rec.policy_type === 'reorder_level';
  const basisValue = manual
    ? rec.reorder_level ?? rec.master_reorder_level ?? null
    : rec.reorder_point ?? null;
  if (basisValue === null || net === null) {
    return { breached: true, basisLabel: null, basisValue: null };
  }
  return {
    breached: net <= basisValue,
    basisLabel: manual ? 'level' : 'reorder point',
    basisValue,
  };
}

/**
 * The forecast add-on's editable-quantity bound (user feedback, 2026-08-12: "what if I
 * don't want to buy 1,200 more, what if 1,500? editable here").
 *
 * Capped at 10x the system's own trend-aware proposal - generous enough for a real change
 * of mind, tight enough to catch a fat-fingered extra digit. A proposal of 0 (or absent)
 * falls back to a flat sane ceiling rather than capping at 0, though in practice the
 * editable row never renders in that case (the caller only offers it when `qty > 0`).
 */
const FORECAST_QTY_FALLBACK_CAP = 99_999;
const FORECAST_QTY_CAP_MULTIPLE = 10;

export function forecastQtyCap(proposedQty: number): number {
  return proposedQty > 0 ? proposedQty * FORECAST_QTY_CAP_MULTIPLE : FORECAST_QTY_FALLBACK_CAP;
}

/** Bounds a buyer-typed add-on quantity: a non-negative integer, never past its cap. */
export function clampForecastQty(raw: number, cap: number): number {
  if (!Number.isFinite(raw)) return 0;
  const rounded = Math.round(raw);
  if (rounded < 0) return 0;
  if (rounded > cap) return cap;
  return rounded;
}
