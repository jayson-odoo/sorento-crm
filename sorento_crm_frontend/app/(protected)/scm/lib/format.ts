/**
 * Number/currency formatting for the SCM dashboard. Right-aligned tabular
 * figures are the "type signature" of the dashboard — deferred values render as
 * an em dash, never a fabricated 0.
 *
 * Phase 1 hard-codes "RM"; Phase 2 will thread the system currency format
 * (`useCurrencyFormat`) through instead.
 */
export const EM_DASH = '—';

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

/** Signed integer — used for net position (deficit shows a leading −). */
export function fmtSigned(value: number | null | undefined): string {
  if (value === null || value === undefined) return EM_DASH;
  const s = intFmt.format(Math.abs(value));
  if (value < 0) return `−${s}`;
  return s;
}

/** Currency valuation. Deferred/uncosted (null) → em dash. */
export function fmtMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return EM_DASH;
  return `RM ${moneyFmt.format(value)}`;
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
 * `—` = nothing meaningful to quote (no demand + no stock, or a deficit).
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

/** Percentage from a 0–1 ratio. null → em dash. */
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
