/**
 * Product health: whether an item is still moving, and whether to keep selling it.
 *
 * > "maybe it is a hot selling item, but the margin is so little ... we need to suggest
 * >  to discontinue or not, looking into multiple factors like the sales, the mobility
 * >  of the stock, is it having good margin, what's the cost, what's the turnover"
 *
 * The margin half of that is gone (captain, 27 Aug): costs are often CNY and selling
 * prices MYR with no exchange rate anyone trusts, so a margin percentage on the plan was
 * an exchange rate wearing a verdict. What is left is MOVEMENT, which the books do agree
 * on - delivery orders out, GRN receipts in:
 *
 *     Fast moving  - sold in the last 3 months AND bought in the last 6
 *     Slow moving  - one of the two, not both
 *     Dead         - neither, and stock still on hand -> "Consider discontinuing"
 *     No history   - neither, and nothing on hand
 *
 * `app/services/scm/product_economics_service.py` draws the class (it is the same four
 * rules whichever side counts them, and the backend is where the movement lives); this
 * file turns it into the words the column says.
 */
import { fmtTrimmedDecimal } from '../../lib/format';

const fmt = (v: number) => fmtTrimmedDecimal(v, 1);

export interface ProductEconomics {
  product_id: string;
  /** Quantity-weighted realized price (MYR), or list price when nothing sold. */
  avg_sell_price: number | null;
  sell_source: 'orders' | 'list_price' | null;
  sold_qty: number;
  on_hand: number;
  avg_monthly_out: number;
  /** Months of stock at the current pace. Null when nothing moves. */
  turnover_months: number | null;
  no_movement: boolean;
  /** The buyer's standing answer to the advisory, or null while undecided. */
  lifecycle_decision: 'keep' | 'discontinue' | null;
  lifecycle_decided_at: string | null;
  /** Delivery-order quantity in the last `sold_window_months`. */
  sold_recent_qty: number;
  /** GRN receipt quantity in the last `bought_window_months`. A PO issued is not a buy. */
  bought_recent_qty: number;
  movement_class: MovementClass;
}

export type MovementClass = 'fast_moving' | 'slow_moving' | 'dead' | 'no_history';

export interface EconomicsPayload {
  products: Record<string, ProductEconomics>;
  count: number;
  thresholds: { margin_floor_pct: number; dead_turnover_months: number };
  sell_window_months: number;
  /** The windows the health class was judged on: 3 months out, 6 months in. */
  sold_window_months?: number;
  bought_window_months?: number;
}

export const MOVEMENT_LABEL: Record<MovementClass, string> = {
  fast_moving: 'Fast moving',
  slow_moving: 'Slow moving',
  dead: 'Dead',
  no_history: 'No history',
};

/** Badge tone per class. Dead is the only one that asks the buyer for anything. */
export const MOVEMENT_TONE: Record<MovementClass, 'success' | 'warning' | 'destructive' | 'secondary'> = {
  fast_moving: 'success',
  slow_moving: 'warning',
  dead: 'destructive',
  no_history: 'secondary',
};

/** Sort weight: the rows the buyer should re-question float to the top of the column. */
export const MOVEMENT_SORT: Record<MovementClass, number> = {
  dead: 0,
  no_history: 1,
  slow_moving: 2,
  fast_moving: 3,
};

export interface HealthVerdict {
  klass: MovementClass;
  label: string;
  tone: 'success' | 'warning' | 'destructive' | 'secondary';
  /** True only for Dead - the one class that carries an ask. */
  consider: boolean;
  /** The line under the pill, or null when the class asks for nothing. */
  suggestion: string | null;
  /** Every fact behind the verdict, with its number - the drill shows the whole case. */
  factors: string[];
}

/**
 * The verdict, its wording and the movement behind it.
 *
 * Every factor names a number. A verdict without its counts is the one thing the buyer
 * said they would not trust, and the counts are the whole case now that margin is gone.
 */
export function healthVerdict(
  econ: ProductEconomics | undefined,
  windows?: { sold_window_months?: number; bought_window_months?: number },
): HealthVerdict | null {
  if (!econ) return null;
  const klass = econ.movement_class;
  const soldMonths = windows?.sold_window_months ?? 3;
  const boughtMonths = windows?.bought_window_months ?? 6;
  const factors = [
    econ.sold_recent_qty > 0
      ? `Sold: ${fmt(econ.sold_recent_qty)} delivered in the last ${fmt(soldMonths)} months.`
      : `Sold: nothing delivered in the last ${fmt(soldMonths)} months.`,
    econ.bought_recent_qty > 0
      ? `Bought: ${fmt(econ.bought_recent_qty)} received in the last ${fmt(boughtMonths)} months.`
      : `Bought: nothing received in the last ${fmt(boughtMonths)} months.`,
    econ.on_hand > 0
      ? `On hand: ${fmt(econ.on_hand)} across every location.`
      : 'On hand: nothing left anywhere.',
  ];
  return {
    klass,
    label: MOVEMENT_LABEL[klass],
    tone: MOVEMENT_TONE[klass],
    consider: klass === 'dead',
    suggestion: klass === 'dead' ? 'Consider discontinuing' : null,
    factors,
  };
}

/**
 * The MOQ pump-up, explained with its sell-through odds.
 *
 * > "if the quantity can't reach MoQ, we need to flag the gap, then suggest to fill the
 * >  gap via what method, maybe promotion? or pump up to MoQ with no hope that the extra
 * >  qty will sell? how likely is it for us to sell the additional quantity"
 *
 * The engine already floors the buy at the MOQ - silently, which is the problem. This
 * names the pump-up: how much was needed, how much the supplier forces, and how long the
 * extra takes to clear at the product's own pace. The judgment ("fine" / "promotion" /
 * "negotiate") keys on the same dead-turnover line the discontinue advisory uses.
 */
export interface MoqGap {
  moq: number;
  /** What the plan actually needed before the MOQ floor. */
  needed: number;
  /** Units forced on top of the need (includes pack rounding above the MOQ). */
  extra: number;
  /** How long the extra takes to sell at the current pace. Null when nothing moves. */
  months_to_clear: number | null;
  verdict: 'clears' | 'slow' | 'no_pace';
  sentence: string;
}

export function moqGap(
  needed: number,
  moq: number | null,
  orderedQty: number,
  econ: ProductEconomics | undefined,
  deadTurnoverMonths: number,
): MoqGap | null {
  if (moq === null || moq <= 0 || needed <= 0 || needed >= moq) return null;
  const extra = Math.max(orderedQty - needed, 0);
  if (extra < 1) return null;
  const pace = econ?.avg_monthly_out ?? 0;
  const months = pace > 0 ? Math.round((extra / pace) * 10) / 10 : null;
  const verdict: MoqGap['verdict'] =
    months === null ? 'no_pace' : months <= deadTurnoverMonths ? 'clears' : 'slow';
  const sentence =
    verdict === 'clears'
      ? `Need ${fmt(needed)}, MOQ forces ${fmt(orderedQty)}: the ${fmt(extra)} extra clears in about ${fmt(months!)} months at the current pace.`
      : verdict === 'slow'
        ? `Need ${fmt(needed)}, MOQ forces ${fmt(orderedQty)}: the ${fmt(extra)} extra is about ${fmt(months!)} months of stock - consider a promotion to move it, or negotiate the MOQ down.`
        : `Need ${fmt(needed)}, MOQ forces ${fmt(orderedQty)}: nothing is selling to clear the ${fmt(extra)} extra - a promotion or a lower MOQ is the honest path.`;
  return { moq, needed, extra, months_to_clear: months, verdict, sentence };
}

/**
 * The short pump-up note shown beside a quantity, reused everywhere a `MoqGap` is rendered
 * (the MOQ column, and the order-qty ledger's THE BUY block, S3) so the wording can never
 * drift between the two. `fmt` is the caller's own integer formatter (`fmtInt`), matching
 * `describeCover`'s pattern of taking the formatter rather than importing one.
 */
export function moqGapNote(gap: MoqGap, fmt: (n: number) => string): string {
  return gap.verdict === 'clears'
    ? `+${fmt(gap.extra)} extra, clears in ~${gap.months_to_clear} mo`
    : gap.verdict === 'slow'
      ? `+${fmt(gap.extra)} extra ≈ ${gap.months_to_clear} mo - promotion?`
      : `+${fmt(gap.extra)} extra, nothing selling to clear it`;
}
