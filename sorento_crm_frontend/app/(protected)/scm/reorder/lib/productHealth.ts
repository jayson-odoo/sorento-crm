/**
 * Product health: the margin an item really earns, and whether to keep selling it.
 *
 * > "maybe it is a hot selling item, but the margin is so little ... we need to suggest
 * >  to discontinue or not, looking into multiple factors like the sales, the mobility
 * >  of the stock, is it having good margin, what's the cost, what's the turnover"
 *
 * Mirrors `app/services/scm/product_economics_service.py`, which states the facts
 * (realized selling price, on hand, pace, months of stock); this file draws the verdicts
 * and the words. Margin compares in the BASE currency - the cost side is the plan's own
 * `unit_cost_base`, the sell side is what customers actually paid in MYR - because a
 * margin across two currencies is an exchange rate wearing a percentage.
 *
 * The discontinue advisory is an ASK built on two hard factors - the demand is dying
 * (trend) AND the stock has stopped moving (turnover past the policy line) - with the
 * margin cited as evidence either way. A thin margin alone never suggests killing a
 * product that still sells; that is a pricing conversation, not a discontinuation.
 */
import type { TrajectoryEntry } from './trajectory';

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
}

export interface EconomicsPayload {
  products: Record<string, ProductEconomics>;
  count: number;
  thresholds: { margin_floor_pct: number; dead_turnover_months: number };
  sell_window_months: number;
}

export type MarginTone = 'healthy' | 'thin' | 'negative' | 'unknown';

export interface MarginVerdict {
  tone: MarginTone;
  /** (sell - cost) / sell, as a percent. Null when either side is unknown. */
  pct: number | null;
  sell: number | null;
  cost: number | null;
  sell_source: 'orders' | 'list_price' | null;
}

export function marginOf(
  costBase: number | null,
  econ: ProductEconomics | undefined,
  floorPct: number,
): MarginVerdict {
  const sell = econ?.avg_sell_price ?? null;
  // Zero cost is the zero_cost price problem, not a 100% margin; unknown, not healthy.
  if (sell === null || costBase === null || costBase <= 0) {
    return { tone: 'unknown', pct: null, sell, cost: costBase, sell_source: econ?.sell_source ?? null };
  }
  const pct = ((sell - costBase) / sell) * 100;
  const tone: MarginTone = pct < 0 ? 'negative' : pct < floorPct ? 'thin' : 'healthy';
  return {
    tone,
    pct: Math.round(pct * 10) / 10,
    sell,
    cost: costBase,
    sell_source: econ?.sell_source ?? null,
  };
}

export interface DiscontinueAdvice {
  consider: boolean;
  /** Every factor with its number, verdict or not - the drill shows the whole case. */
  factors: string[];
}

const fmt = (v: number) =>
  v.toLocaleString(undefined, { maximumFractionDigits: 1 });

export function discontinueAdvice(
  econ: ProductEconomics | undefined,
  margin: MarginVerdict,
  trend: TrajectoryEntry | undefined,
  thresholds: { margin_floor_pct: number; dead_turnover_months: number },
): DiscontinueAdvice | null {
  if (!econ) return null;

  const demandDying =
    econ.no_movement || trend?.verdict === 'falling' || trend?.verdict === 'quiet';
  const turnoverDead =
    econ.turnover_months !== null
      ? econ.turnover_months > thresholds.dead_turnover_months
      : econ.no_movement && econ.on_hand > 0;

  const consider = demandDying && turnoverDead;

  const factors: string[] = [];
  factors.push(
    econ.no_movement
      ? 'Sales: nothing left this product in the last 12 months.'
      : `Sales: ${fmt(econ.sold_qty)} sold in the last 12 months (${fmt(econ.avg_monthly_out)} a month)${
          trend?.verdict === 'falling' ? ', and falling' :
          trend?.verdict === 'rising' ? ', and rising' : ''
        }.`,
  );
  factors.push(
    econ.turnover_months === null
      ? econ.on_hand > 0
        ? `Turnover: ${fmt(econ.on_hand)} on hand and no movement to clear it.`
        : 'Turnover: nothing on hand, nothing moving.'
      : `Turnover: ${fmt(econ.on_hand)} on hand is ${fmt(econ.turnover_months)} months of stock (the line is ${fmt(thresholds.dead_turnover_months)}).`,
  );
  factors.push(
    margin.pct === null
      ? 'Margin: unknown - a selling price or a cost is missing.'
      : `Margin: ${margin.pct}% (sells ${fmt(margin.sell ?? 0)}, costs ${fmt(margin.cost ?? 0)})${
          margin.tone === 'healthy'
            ? consider
              ? ' - the one thing in its favour'
              : ''
            : `, below the ${fmt(thresholds.margin_floor_pct)}% floor`
        }.`,
  );
  if (margin.cost !== null && econ.on_hand > 0) {
    factors.push(`Cash tied up: ${fmt(econ.on_hand * margin.cost)} sitting in stock.`);
  }

  return { consider, factors };
}
