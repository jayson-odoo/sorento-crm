/**
 * Decimal-safe arithmetic on the money and quantity STRINGS the PO intake contract sends.
 *
 * Why not `Number(value)`: the whole point of the confirm screen is the difference between
 * our sum of 52 lines and the total printed on the paper. A float sum of 52 two-decimal
 * values drifts, and a drift of one cent presented as "the document disagrees with us" is a
 * false alarm that teaches people to ignore the banner.
 *
 * Everything below parses the string into a SCALED INTEGER (cents, or ten-thousandths for
 * quantity) by splitting on the decimal point, never by parsing a float. Integers are held
 * in `number` rather than `bigint` deliberately: this project's largest total is 1.81 million
 * ringgit, which is 181,064,062 cents, and the widest intermediate is a quantity in
 * ten-thousandths times a price in cents (about 3.6e11). Both are exact integers far below
 * 2^53, and `bigint` literals are not available at this repo's ES2017 target.
 */

const MONEY_DP = 2;
const QTY_DP = 4;

interface Scaled {
  units: number;
  dp: number;
}

/** Splits on the decimal point. Returns null for anything that is not a plain decimal. */
function parseScaled(value: string | null | undefined, dp: number): Scaled | null {
  if (value === null || value === undefined) return null;
  const trimmed = String(value).trim();
  if (trimmed === '') return null;
  const match = /^([+-]?)(\d*)(?:\.(\d*))?$/.exec(trimmed);
  if (!match) return null;
  const [, sign, whole, fraction = ''] = match;
  if (whole === '' && fraction === '') return null;
  const padded = (fraction + '0'.repeat(dp)).slice(0, dp);
  const digits = `${whole || '0'}${padded}`;
  const units = Number(digits);
  if (!Number.isFinite(units) || !Number.isSafeInteger(units)) return null;
  return { units: sign === '-' ? -units : units, dp };
}

function formatScaled({ units, dp }: Scaled): string {
  const negative = units < 0;
  const digits = String(Math.abs(units)).padStart(dp + 1, '0');
  const whole = digits.slice(0, digits.length - dp);
  const fraction = dp > 0 ? `.${digits.slice(digits.length - dp)}` : '';
  return `${negative ? '-' : ''}${whole}${fraction}`;
}

/** True when the string is a decimal we can do arithmetic on. */
export function isDecimalString(value: string | null | undefined): boolean {
  return parseScaled(value, MONEY_DP) !== null;
}

/** Sum of money strings, to the cent. Null when any input is not a decimal. */
export function sumMoney(values: Array<string | null | undefined>): string | null {
  let cents = 0;
  for (const value of values) {
    const parsed = parseScaled(value, MONEY_DP);
    if (!parsed) return null;
    cents += parsed.units;
  }
  return formatScaled({ units: cents, dp: MONEY_DP });
}

/** `a - b`, signed, to the cent. */
export function subtractMoney(
  a: string | null | undefined,
  b: string | null | undefined,
): string | null {
  const left = parseScaled(a, MONEY_DP);
  const right = parseScaled(b, MONEY_DP);
  if (!left || !right) return null;
  return formatScaled({ units: left.units - right.units, dp: MONEY_DP });
}

/** -1, 0 or 1. Null when either side is not a decimal. */
export function compareMoney(
  a: string | null | undefined,
  b: string | null | undefined,
): -1 | 0 | 1 | null {
  const left = parseScaled(a, MONEY_DP);
  const right = parseScaled(b, MONEY_DP);
  if (!left || !right) return null;
  if (left.units === right.units) return 0;
  return left.units < right.units ? -1 : 1;
}

/** `qty * unit_price`, rounded to the cent, which is what an amount column holds. */
export function multiplyMoney(
  qty: string | null | undefined,
  unitPrice: string | null | undefined,
): string | null {
  const quantity = parseScaled(qty, QTY_DP);
  const price = parseScaled(unitPrice, MONEY_DP);
  if (!quantity || !price) return null;
  const scaled = quantity.units * price.units; // scale = QTY_DP + MONEY_DP
  if (!Number.isSafeInteger(scaled)) return null;
  const divisor = 10 ** QTY_DP;
  const cents = Math.round(Math.abs(scaled) / divisor) * (scaled < 0 ? -1 : 1);
  return formatScaled({ units: cents, dp: MONEY_DP });
}

export function isMoneyZero(value: string | null | undefined): boolean {
  const parsed = parseScaled(value, MONEY_DP);
  return parsed ? parsed.units === 0 : false;
}

/**
 * The glyph a currency code is written with: ringgit reads `RM`, anything else reads its
 * own code. A blank code predates the book having more than one currency, so it already
 * meant ringgit. Same rule as `scm/lib/format.ts`'s own label, restated here rather than
 * imported because a shared project-sales helper must not reach into an SCM screen.
 */
function currencyLabel(currency: string | null | undefined): string {
  const code = (currency || '').trim().toUpperCase();
  return code === '' || code === 'MYR' ? 'RM' : code;
}

/**
 * `RM 1,810,640.62` / `USD 12.50`, grouped from the STRING. Nothing is parsed as a float on
 * the way to the screen either, so a value the backend sent as `1810640.62` is never
 * rendered as `1810640.6200000001`.
 *
 * `currency` is a PARAMETER rather than a second formatter because the purchase-order book
 * is mostly USD (8,438 lines against 4,186 MYR), and printing a USD line as `RM 12.50` is a
 * wrong number stated as a fact next to a document that says otherwise.
 */
export function formatMoneyExact(
  value: string | null | undefined,
  currency?: string | null,
): string {
  const parsed = parseScaled(value, MONEY_DP);
  if (!parsed) return value ? String(value) : '-';
  const negative = parsed.units < 0;
  const digits = String(Math.abs(parsed.units)).padStart(MONEY_DP + 1, '0');
  const whole = digits.slice(0, digits.length - MONEY_DP);
  const fraction = digits.slice(digits.length - MONEY_DP);
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return `${negative ? '-' : ''}${currencyLabel(currency)} ${grouped}.${fraction}`;
}

/** The same figure in the currency everything in project sales is quoted in. */
export function formatMyrExact(value: string | null | undefined): string {
  return formatMoneyExact(value, 'MYR');
}

/** A quantity as written, with trailing decimal zeros dropped: `927`, not `927.0000`. */
export function formatQty(value: string | null | undefined): string {
  const parsed = parseScaled(value, QTY_DP);
  if (!parsed) return value ? String(value) : '-';
  const text = formatScaled(parsed);
  return text.includes('.') ? text.replace(/\.?0+$/, '') : text;
}
