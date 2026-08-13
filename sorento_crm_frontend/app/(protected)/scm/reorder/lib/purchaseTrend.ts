/**
 * The mirror of the order trend, on the buy side: who we bought it from, and when.
 *
 * > "similar to SO - what is the trend of purchase, then the list of supplier, purchase
 * >  date, purchase quantity, purchase cost" (user markup, 2026-08-11)
 *
 * Mirrors `app/services/scm/purchase_trend_service.py`, which states the facts (the
 * recent-vs-previous window sums and the recent lines); this file only turns them into
 * words, same split as `trajectory.ts` and `priceAdvice.ts`.
 */
import { fmtInt } from '../../lib/format';

export interface PurchaseTrendLine {
  supplier_code: string | null;
  supplier_name: string | null;
  po_number: string | null;
  order_date: string | null;
  qty: number;
  unit_cost: number | null;
  currency: string | null;
}

export interface ProductPurchaseTrend {
  recent_qty: number;
  previous_qty: number;
  lines: PurchaseTrendLine[];
}

export interface PurchaseTrendPayload {
  window_months: number;
  products: Record<string, ProductPurchaseTrend>;
}

/**
 * "Purchased 400 in the last 3 months, 1,200 in the 3 months before." Numbers carry their
 * meaning, same rule as the order-trend headline: a bare percentage would not.
 */
export function describePurchaseTrend(
  t: ProductPurchaseTrend | undefined,
  windowMonths: number,
): string {
  if (!t || (t.recent_qty === 0 && t.previous_qty === 0 && t.lines.length === 0)) {
    return 'Never purchased in the imported history.';
  }
  const w = windowMonths;
  const windowWord = `${w} month${w === 1 ? '' : 's'}`;
  return `Purchased ${fmtInt(t.recent_qty)} in the last ${windowWord}, ${fmtInt(t.previous_qty)} in the ${windowWord} before.`;
}
