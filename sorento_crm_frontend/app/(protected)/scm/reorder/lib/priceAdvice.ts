/**
 * What we last paid, how old that is, and whether to go back for a quote.
 *
 * > "the purchase cost that we are going to use now, another decision point ... should i
 * >  use the last price, or should i rfq to get new price from supplier ... of course, the
 * >  system need to suggest to a certain extent, but i am not sure how smart can we suggest
 * >  whether to use the same price or need new price cause we are blind to market condition"
 *
 * The buyer drew the boundary and this module stays inside it. Every sentence here is about
 * OUR OWN purchase ledger and its age. Nothing claims to know what the item is worth today,
 * because nothing in this system can see that.
 *
 * Mirrors `app/services/scm/price_history_service.py`, which decides the codes; this file
 * only turns them into words. The split is deliberate - a backend that ships prose ends up
 * owning the tone of a screen it cannot see.
 */

export interface PricePurchase {
  po_number: string | null;
  issue_date: string | null;
  unit_cost: number;
  currency: string | null;
  qty: number | null;
}

export type PriceAdviceCode =
  /** The plan is costing this line at 0.00. Loudest of the lot: it funds for nothing. */
  | 'zero_cost'
  /** Never bought from this supplier. Not the same as an old price. */
  | 'no_history'
  /** A price with no date on it, so its age cannot be vouched for. */
  | 'unknown_age'
  /** Older than the window the business treats as current. */
  | 'stale'
  /** Recent, but it moved between our last two purchases. */
  | 'moving'
  /** Recent and holding. Reuse it. */
  | 'recent';

export interface PriceAdvice {
  advice: PriceAdviceCode;
  last: PricePurchase | null;
  previous: PricePurchase | null;
  age_days: number | null;
  movement_pct: number | null;
  currency_changed: boolean;
  standing_cost: number | null;
  standing_currency: string | null;
  standing_gap_pct: number | null;
  free_of_charge_lines: number;
}

export interface PriceHistoryPayload {
  stale_after_days: number;
  movement_threshold_pct: number;
  prices: Record<string, PriceAdvice>;
}

/** The one-word column label. Short enough for a grid cell, specific enough to act on. */
export const PRICE_ADVICE_LABEL: Record<PriceAdviceCode, string> = {
  zero_cost: 'Priced at zero',
  no_history: 'Never bought',
  unknown_age: 'Undated price',
  stale: 'Re-quote',
  moving: 'Price moving',
  recent: 'Price current',
};

/**
 * How loud the row should be.
 *
 * `no_history` is neutral, not a warning: buying from a new supplier is normal, and there is
 * nothing wrong to fix. A zero cost IS wrong, and says so.
 */
export const PRICE_ADVICE_TONE: Record<PriceAdviceCode, 'danger' | 'warning' | 'neutral' | 'ok'> = {
  zero_cost: 'danger',
  stale: 'warning',
  moving: 'warning',
  unknown_age: 'warning',
  no_history: 'neutral',
  recent: 'ok',
};

/**
 * Sort order for the column: most urgent price question first.
 *
 * Not alphabetical. A line the plan is costing at zero has to be one click from the top,
 * and "Never bought" sorting above "Re-quote" would bury the six-year-old prices under a
 * thousand rows where nothing is actually wrong.
 */
export const PRICE_ADVICE_SORT: Record<PriceAdviceCode, number> = {
  zero_cost: 0,
  unknown_age: 1,
  stale: 2,
  moving: 3,
  no_history: 4,
  recent: 5,
};

/** Days as something a person says out loud. `840` means nothing; "2 years 4 months" does. */
export function humanAge(days: number | null): string | null {
  if (days === null || days === undefined) return null;
  if (days < 0) return 'dated in the future';
  if (days < 45) return `${days} day${days === 1 ? '' : 's'} ago`;
  const months = Math.round(days / 30.44);
  if (months < 24) return `${months} months ago`;
  const years = Math.floor(days / 365.25);
  const rem = Math.round((days - years * 365.25) / 30.44);
  return rem > 0 ? `${years} years ${rem} months ago` : `${years} years ago`;
}

function money(amount: number, currency: string | null): string {
  const n = amount.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return currency ? `${currency} ${n}` : n;
}

/** "USD 20.37 on 202012-S0048, 2020-12-15" - the fact, with its receipt. */
export function describeLastPurchase(p: PricePurchase | null): string | null {
  if (!p) return null;
  const parts = [money(p.unit_cost, p.currency)];
  if (p.po_number) parts.push(`on ${p.po_number}`);
  if (p.issue_date) parts.push(p.issue_date);
  return parts.join(', ');
}

/**
 * The recommendation, in a sentence, with the evidence for it attached.
 *
 * Every branch names a fact and stops. "Older than N months, so quote it" is a statement
 * about our records; "prices have risen" would be a statement about a market this system
 * has never seen, and is the one thing it must never say.
 */
export function describePriceAdvice(a: PriceAdvice | undefined, staleAfterDays: number): string {
  if (!a) return 'No price information for this supplier.';
  const paid = describeLastPurchase(a.last);
  const age = humanAge(a.age_days);

  switch (a.advice) {
    case 'zero_cost':
      return paid
        ? `The plan is costing this at zero. The last price we actually paid was ${paid}, ${age}. Price it before ordering.`
        : 'The plan is costing this at zero, so any quantity looks free. Price it before ordering.';
    case 'no_history':
      return 'No purchase from this supplier on record. Ask them to quote.';
    case 'unknown_age':
      return `We paid ${paid}, but the order carries no date, so how current it is cannot be checked. Confirm it with the supplier.`;
    case 'stale':
      return `We last paid ${paid}, ${age}. That is past the ${Math.round(staleAfterDays / 30.44)} month mark, so ask for a fresh quote.`;
    case 'moving':
      return `We last paid ${paid}, ${age}. It ${a.movement_pct !== null && a.movement_pct >= 0 ? 'rose' : 'fell'} ${Math.abs(a.movement_pct ?? 0).toFixed(1)}% from the purchase before it, so confirm the price.`;
    case 'recent':
    default:
      return `We last paid ${paid}, ${age}. Recent enough to reuse.`;
  }
}

/** Notes worth reading but not worth a headline. Empty when there is nothing to add. */
export function priceFootnotes(a: PriceAdvice | undefined): string[] {
  if (!a) return [];
  const out: string[] = [];
  if (a.previous && a.movement_pct !== null) {
    out.push(
      `Before that: ${describeLastPurchase(a.previous)} (${a.movement_pct >= 0 ? '+' : ''}${a.movement_pct.toFixed(1)}% since).`,
    );
  }
  if (a.currency_changed) {
    out.push('The two purchases were billed in different currencies, so no price movement is claimed.');
  }
  if (a.standing_gap_pct !== null && a.standing_gap_pct !== 0) {
    out.push(
      `The plan is costing this ${Math.abs(a.standing_gap_pct).toFixed(1)}% ${a.standing_gap_pct > 0 ? 'below' : 'above'} what we last paid.`,
    );
  }
  if (a.free_of_charge_lines > 0) {
    out.push(
      `${a.free_of_charge_lines} line${a.free_of_charge_lines === 1 ? '' : 's'} from this supplier recorded no charge and ${a.free_of_charge_lines === 1 ? 'was' : 'were'} left out of the price.`,
    );
  }
  return out;
}

/** The key both the plan row and the price map agree on. */
export function priceKey(productId: string | null, supplierCode: string | null): string | null {
  if (!productId || !supplierCode) return null;
  return `${productId}:${supplierCode}`;
}
