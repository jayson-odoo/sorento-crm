/**
 * The row's line cost, in the currency the number is actually being read in (S11, round 2).
 *
 * Before this the row costed a buy at `unit_cost_base` (the supplier's price restated in
 * ringgit for the cash tiles) and printed it under "at last price" whenever "Use last
 * price" was selected - regardless of whether that figure was actually the last price we
 * paid. On SRTSS8710 the two disagreed by 2.5x (RM 121.80 default-link cost vs CNY 48.00
 * actually paid to KAIPING HANSHUN), so the row stated a fact about the wrong number.
 *
 * This reads the LAST PURCHASE figure the row's decision claims to be using, in ITS OWN
 * currency, and falls back to the chosen supplier's own quoted cost - never to the
 * base-currency conversion, which is a budgeting figure, not a price anyone was quoted.
 */
import type { PlanRowPriceMode } from '../types/decisions.types';

export interface LineCostMoney {
  unit_cost: number | null | undefined;
  currency?: string | null;
}

export interface LineCostResult {
  amount: number;
  currency: string | null;
  basis: 'last' | 'supplier';
}

export function lineCost({
  buyQty,
  priceMode,
  last,
  supplier,
}: {
  buyQty: number;
  priceMode: PlanRowPriceMode;
  /** The row's actual last purchase, whoever it was bought from. Null = never bought. */
  last: LineCostMoney | null | undefined;
  /** The currently chosen supplier's own quoted cost, in their own currency. */
  supplier: LineCostMoney | null | undefined;
}): LineCostResult | null {
  if (priceMode === 'use_last' && last && last.unit_cost !== null && last.unit_cost !== undefined) {
    return { amount: buyQty * last.unit_cost, currency: last.currency ?? null, basis: 'last' };
  }
  if (supplier && supplier.unit_cost !== null && supplier.unit_cost !== undefined) {
    return { amount: buyQty * supplier.unit_cost, currency: supplier.currency ?? null, basis: 'supplier' };
  }
  return null;
}
