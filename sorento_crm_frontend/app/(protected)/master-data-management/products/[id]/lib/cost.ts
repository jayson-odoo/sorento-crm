/**
 * Money formatting for the product page's cost, shared by the Overview summary and the
 * Purchase History tab so the two can never disagree about the same figure.
 *
 * The currency is whatever the order was raised in and is always shown. Nothing here
 * converts: a CNY order restated in ringgit needs a rate, and a rate we do not have must
 * never be silently assumed to be 1.
 */

/** Said wherever a figure has no currency behind it.
 *
 *  Everything else on this page is quoted in ringgit, so a bare number on an order that
 *  recorded no currency would be read as ringgit. It may not be, and a wrong currency is a
 *  wrong price. */
export const NO_CURRENCY_NOTE = 'currency not recorded on the order';

/** `1,234.56 CNY`, or `RM 1,234.56` when the order was in ringgit. `-` for no figure. */
export function formatUnitCost(
  value: number | null | undefined,
  currency: string | null | undefined,
): string {
  if (value == null || Number.isNaN(value)) return '-';
  const amount = new Intl.NumberFormat('en-MY', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
  if (!currency) return amount;
  return currency.toUpperCase() === 'MYR' ? `RM ${amount}` : `${amount} ${currency}`;
}
