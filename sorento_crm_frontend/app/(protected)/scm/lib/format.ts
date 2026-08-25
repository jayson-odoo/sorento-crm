/**
 * Number/currency formatting for the SCM dashboard. Right-aligned tabular
 * figures are the "type signature" of the dashboard - deferred values render as
 * an em dash, never a fabricated 0.
 *
 * Phase 1 hard-codes "RM"; Phase 2 will thread the system currency format
 * (`useCurrencyFormat`) through instead.
 */
// A plain hyphen, deliberately. Em-dashes are banned in this codebase's writing and the
// user does not want to see them in the UI either.
export const EM_DASH = '-';

const intFmt = new Intl.NumberFormat('en-MY', { maximumFractionDigits: 0 });
const moneyFmt = new Intl.NumberFormat('en-MY', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

/** Integer with thousands separators. Deferred (null) → em dash. */
export function fmtInt(value: number | null | undefined): string {
  if (value === null || value === undefined) return EM_DASH;
  return intFmt.format(value);
}

/** Signed integer - used for net position (deficit shows a leading −). */
export function fmtSigned(value: number | null | undefined): string {
  if (value === null || value === undefined) return EM_DASH;
  const s = intFmt.format(Math.abs(value));
  if (value < 0) return `−${s}`;
  return s;
}

/**
 * The currency every figure on this dashboard is reported in: valuations, the budget,
 * cash impact. Mirrors `app.services.scm.money.BASE_CURRENCY` on the backend.
 */
export const BASE_CURRENCY = 'MYR';

/**
 * Is this figure already in the currency everything is reported in?
 *
 * A missing code counts as base: a row predating the book having more than one currency
 * already meant ringgit. Exported so a caller can decide whether restating a price in base
 * adds anything, without restating the "blank means base" rule for itself.
 */
export function isBaseCurrency(currency: string | null | undefined): boolean {
  const code = (currency || '').trim().toUpperCase();
  return code === '' || code === BASE_CURRENCY;
}

/** The glyph a currency code is written with. Base currency reads `RM`, anything else
 *  reads its own code, so a figure never claims a currency it is not in. */
function currencyLabel(currency: string | null | undefined): string {
  if (isBaseCurrency(currency)) return 'RM';
  return (currency || '').trim().toUpperCase();
}

/** Currency valuation, in the base currency. Deferred/uncosted (null) → em dash. */
export function fmtMoney(value: number | null | undefined): string {
  return fmtMoneyIn(value, null);
}

/**
 * A whole-ringgit-scale figure in the currency it is actually in: `RM 1,980`, `USD 1,980`.
 *
 * The rounded sibling of `fmtSupplierCost`. Cash committed, a budget or a valuation is read
 * at a glance and its cents are noise, but the currency is not: the PO book is mostly USD,
 * and `RM 1,980` against a USD purchase order is a wrong number printed as a fact. A row
 * with no currency code predates the book having more than one, so it already meant ringgit.
 */
export function fmtMoneyIn(
  value: number | null | undefined,
  currency: string | null | undefined,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EM_DASH;
  return `${currencyLabel(currency)} ${moneyFmt.format(value)}`;
}

const costFmt = new Intl.NumberFormat('en-MY', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/**
 * A price in the SUPPLIER's own currency.
 *
 * `fmtMoney` hard-codes RM, and the purchase-order book is 8438 lines USD against 4186
 * MYR: rendering a USD price as "RM 45" is a wrong number printed as a fact, sitting next
 * to a purchase order that says otherwise. Cents are kept because a unit price of 4.35 is
 * not 4.
 *
 * A row carrying no currency code predates the book having more than one, so its figure
 * already meant ringgit and reads as base.
 */
export function fmtSupplierCost(
  value: number | null | undefined,
  currency: string | null | undefined,
): string {
  if (value === null || value === undefined) return EM_DASH;
  return `${currencyLabel(currency)} ${costFmt.format(value)}`;
}

/**
 * The same figure with NO currency label, for a price whose currency is genuinely unknown.
 *
 * `fmtSupplierCost` reads a blank code as base and writes `RM`, which is right for the old
 * single-currency rows and wrong for a price that arrived without one: the label would be a
 * claim nobody made. An unlabelled number says only what is known.
 */
export function fmtCostNoCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined) return EM_DASH;
  return costFmt.format(value);
}

/** Short relative "days ago" for last-movement; null → em dash. */
export function fmtDaysAgo(iso: string | null | undefined): string {
  if (!iso) return EM_DASH;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return EM_DASH;
  const days = Math.floor((Date.now() - then) / 86_400_000);
  if (days <= 0) return 'today';
  if (days === 1) return '1 day ago';
  if (days < 60) return `${days} days ago`;
  const months = Math.floor(days / 30);
  return `${months} mo ago`;
}

/** Infinity glyph for days-of-cover when there's stock but no demand. */
export const INFINITY = '∞';

/**
 * Days-of-cover cell text. `∞` = stock on hand with no demand (never runs out);
 * `-` = nothing meaningful to quote (no demand + no stock, or a deficit).
 */
export function fmtDoc(days: number | null | undefined, infinite: boolean): string {
  if (infinite) return INFINITY;
  if (days === null || days === undefined) return EM_DASH;
  return intFmt.format(days);
}

/** Fixed-decimal number (avg daily demand). null → em dash. */
export function fmtDecimal(value: number | null | undefined, dp = 1): string {
  if (value === null || value === undefined) return EM_DASH;
  return value.toLocaleString('en-MY', {
    minimumFractionDigits: dp,
    maximumFractionDigits: dp,
  });
}

const trimmedFmt = new Map<number, Intl.NumberFormat>();

/**
 * A number to AT MOST `dp` decimals, trailing zeros trimmed, so 11.0 reads `11`.
 *
 * The arithmetic lines ("11 × 45 + 300 = 795") read as arithmetic only when a whole number
 * is written whole; `fmtDecimal` pads to a fixed width instead, which is right in a column
 * and wrong in a sentence.
 */
export function fmtTrimmedDecimal(value: number | null | undefined, dp = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EM_DASH;
  let fmt = trimmedFmt.get(dp);
  if (!fmt) {
    fmt = new Intl.NumberFormat('en-MY', { maximumFractionDigits: dp });
    trimmedFmt.set(dp, fmt);
  }
  return fmt.format(Number(value.toFixed(dp)));
}

/** Percentage from a 0-1 ratio. null → em dash. */
export function fmtPct(ratio: number | null | undefined, dp = 0): string {
  if (ratio === null || ratio === undefined) return EM_DASH;
  return `${(ratio * 100).toLocaleString('en-MY', {
    minimumFractionDigits: dp,
    maximumFractionDigits: dp,
  })}%`;
}

/** Absolute short date (e.g. incoming PO ETA). null → em dash. */
/**
 * The one date shape this product uses: `dd/mm/yyyy`.
 *
 * Exported so every other SCM formatter (the coverage timeline's day label, the plan
 * header's run stamp) builds on the SAME parts rather than restating them. Three copies of
 * "a date" is how one screen came to read `07 Jan 2020` while the rest of the app read
 * `07/01/2020`, and a reader cannot tell a deliberate difference from an accidental one.
 *
 * `en-GB` because it orders day before month, which is what Malaysia writes; `2-digit` on
 * both because `7/1/2020` is ambiguous to anybody who reads month-first.
 */
export const DATE_PARTS = {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
} as const;

export const DATE_LOCALE = 'en-GB';

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return EM_DASH;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return EM_DASH;
  return d.toLocaleDateString(DATE_LOCALE, DATE_PARTS);
}

/** 24-hour, both parts padded: `21:05`, and `09:28` rather than `9:28`. No am/pm to
 *  misread, and the same 2-digit reasoning as `DATE_PARTS`. */
export const TIME_PARTS = {
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
} as const;

/**
 * A date WITH its time, for the stamps where the hour matters (when a simulation last ran,
 * when a baseline was blessed). Two runs on the same day are otherwise indistinguishable.
 *
 * The date half is `fmtDate`'s, part for part: this product writes a date one way, and a
 * stamp reading `15 Aug 2026` beside a column of `15/08/2026` looks like a deliberate
 * distinction that nobody made.
 */
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return EM_DASH;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return EM_DASH;
  return `${d.toLocaleDateString(DATE_LOCALE, DATE_PARTS)}, ${d.toLocaleTimeString(DATE_LOCALE, TIME_PARTS)}`;
}

/**
 * A quantity rendered at its own precision: never padded, never truncated. `dp` is the
 * frozen `uom_decimal_places` of the row (0-4). Lives here, not next to its callers,
 * because this file is the one home for number formatting (see format.guard.test.ts).
 */
export function fmtQty(value: number | null | undefined, dp = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return EM_DASH;
  return new Intl.NumberFormat('en-GB', {
    minimumFractionDigits: 0,
    maximumFractionDigits: Math.min(Math.max(dp, 0), 4),
  }).format(value);
}
