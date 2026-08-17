/**
 * The ARBITRARY-PRECISION money variant, and deliberately not `_shared/lib/money`.
 *
 * The standard module is fixed-scale (2dp money, 4dp quantity), which is right for
 * quotations and PO intake. Sales-order documents carry unit prices with MORE than two
 * decimals as printed, and `formatUnitPrice` here preserves them; collapsing the two
 * modules would either lose those digits or push arbitrary-scale parsing onto every
 * screen that never needs it. Anything NOT specific to >2dp documents belongs in
 * `_shared/lib/money`.
 *

 * Decimal-string arithmetic and formatting for the sales order screens.
 *
 * Money and quantities arrive as strings ("392.85000", "1441735.07") and stay strings.
 * Nothing here goes through Number(): summing 99 lines as doubles drifts, and
 * re-serialising a parsed float is how cents disappear off a 1.8 million ringgit order.
 * Addition and comparison scale both operands to a common number of decimals and use
 * BigInt, which is exact for any size these documents reach.
 *
 * Lives in a .tsx file with no JSX so it sits beside the components that use it, matching
 * `formatMyr` living in QuotationsPanel.
 */

// BigInt literals (0n) need target ES2020; this project targets ES2017, so the constants are
// built with the BigInt() constructor instead.
const ZERO = BigInt(0);
const TWO = BigInt(2);
const TEN = BigInt(10);

interface Scaled {
  negative: boolean;
  digits: bigint;
  scale: number;
}

function scaleOf(value: string | null | undefined): Scaled | null {
  const raw = (value ?? '').trim();
  if (!raw) return null;
  const match = /^([+-]?)(\d*)(?:\.(\d*))?$/.exec(raw);
  if (!match) return null;
  const [, sign, whole, fraction = ''] = match;
  if (!whole && !fraction) return null;
  const digits = BigInt(`${whole || '0'}${fraction}`);
  return { negative: sign === '-' && digits !== ZERO, digits, scale: fraction.length };
}

function toScale(value: Scaled, scale: number): bigint {
  const shift = TEN ** BigInt(scale - value.scale);
  const magnitude = value.digits * shift;
  return value.negative ? -magnitude : magnitude;
}

function render(magnitude: bigint, scale: number): string {
  const negative = magnitude < ZERO;
  const digits = (negative ? -magnitude : magnitude).toString().padStart(scale + 1, '0');
  const whole = digits.slice(0, digits.length - scale) || '0';
  const fraction = scale > 0 ? digits.slice(digits.length - scale) : '';
  return `${negative ? '-' : ''}${whole}${fraction ? `.${fraction}` : ''}`;
}

/** Exact sum of decimal strings. Unparseable entries are skipped, never coerced to 0.00. */
export function sumMoney(values: (string | null | undefined)[]): string {
  const parsed = values.map(scaleOf).filter((entry): entry is Scaled => entry !== null);
  if (parsed.length === 0) return '0';
  const scale = parsed.reduce((max, entry) => Math.max(max, entry.scale), 0);
  const total = parsed.reduce((sum, entry) => sum + toScale(entry, scale), ZERO);
  return render(total, scale);
}

/** -1, 0 or 1. Used to decide whether a value changed, never to sort by a float. */
export function compareMoney(a: string | null | undefined, b: string | null | undefined): number {
  const left = scaleOf(a);
  const right = scaleOf(b);
  if (!left || !right) return (a ?? '') === (b ?? '') ? 0 : NaN;
  const scale = Math.max(left.scale, right.scale);
  const l = toScale(left, scale);
  const r = toScale(right, scale);
  return l === r ? 0 : l < r ? -1 : 1;
}

export function isZeroMoney(value: string | null | undefined): boolean {
  const parsed = scaleOf(value);
  return parsed !== null && parsed.digits === ZERO;
}

function group(whole: string): string {
  return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/** Rounds half-up to `dp` decimals on the digits, without ever building a float. */
function roundTo(value: Scaled, dp: number): { whole: string; fraction: string; negative: boolean } {
  if (value.scale <= dp) {
    const padded = value.digits.toString().padStart(value.scale + 1, '0');
    const whole = padded.slice(0, padded.length - value.scale) || '0';
    const fraction = (value.scale > 0 ? padded.slice(padded.length - value.scale) : '').padEnd(dp, '0');
    return { whole, fraction, negative: value.negative };
  }
  const drop = TEN ** BigInt(value.scale - dp);
  const quotient = value.digits / drop;
  const remainder = value.digits % drop;
  const rounded = remainder * TWO >= drop ? quotient + BigInt(1) : quotient;
  const padded = rounded.toString().padStart(dp + 1, '0');
  return {
    whole: padded.slice(0, padded.length - dp) || '0',
    fraction: dp > 0 ? padded.slice(padded.length - dp) : '',
    negative: value.negative,
  };
}

/** "1441735.07" -> "RM 1,441,735.07". Non-numeric input is returned untouched. */
export function formatMoney(value: string | null | undefined): string {
  const parsed = scaleOf(value);
  if (!parsed) return value ?? '';
  const { whole, fraction, negative } = roundTo(parsed, 2);
  return `${negative ? '-' : ''}RM ${group(whole)}${fraction ? `.${fraction}` : ''}`;
}

/** Unit price: two decimals minimum, more only when the document carries them. */
export function formatUnitPrice(value: string | null | undefined): string {
  const parsed = scaleOf(value);
  if (!parsed) return value ?? '';
  const exact = render(parsed.negative ? -parsed.digits : parsed.digits, parsed.scale);
  const [whole, fraction = ''] = exact.replace('-', '').split('.');
  const trimmed = fraction.replace(/0+$/, '');
  const shown = trimmed.length >= 2 ? trimmed : trimmed.padEnd(2, '0');
  return `${parsed.negative ? '-' : ''}${group(whole)}.${shown}`;
}

/** "1800" -> "1,800"; "135.500" -> "135.5". Quantities keep only meaningful decimals. */
export function formatQty(value: string | null | undefined): string {
  const parsed = scaleOf(value);
  if (!parsed) return value ?? '';
  const exact = render(parsed.negative ? -parsed.digits : parsed.digits, parsed.scale);
  const [whole, fraction = ''] = exact.replace('-', '').split('.');
  const trimmed = fraction.replace(/0+$/, '');
  return `${parsed.negative ? '-' : ''}${group(whole)}${trimmed ? `.${trimmed}` : ''}`;
}
