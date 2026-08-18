/**
 * Quantity precision, owned by the UOM (plan section 6.4, AC-F12).
 *
 * A count unit and a measure unit are not the same kind of number: `2.5 EA` is
 * nonsense and `2.5 kg` is a Tuesday. The divisibility lives on the unit of measure
 * as `decimal_places` (0..4) and is FROZEN onto each summary row as
 * `uom_decimal_places` when the run is calculated, so a later edit of the UOM cannot
 * change what a frozen run accepted.
 *
 * The screen validates against the FROZEN snapshot for exactly that reason, and the
 * server validates it again - this is a first line, never the only one. A missing
 * snapshot resolves to 0 during rollout, which is the same fallback the backend uses.
 */

/** The rollout fallback: a row with no frozen snapshot is a whole-unit row. */
export const DEFAULT_DECIMAL_PLACES = 0;

/** Decimal places allowed, from a possibly-absent frozen snapshot. */
export function decimalPlacesOf(frozen: number | null | undefined): number {
  if (frozen === null || frozen === undefined) return DEFAULT_DECIMAL_PLACES;
  if (!Number.isFinite(frozen)) return DEFAULT_DECIMAL_PLACES;
  return Math.min(Math.max(Math.trunc(frozen), 0), 4);
}

/** How many fractional digits a typed quantity actually carries. */
export function decimalsIn(text: string): number {
  const dot = text.indexOf('.');
  if (dot < 0) return 0;
  return text.slice(dot + 1).replace(/0+$/, '').length;
}

/**
 * Keeps a quantity field typeable at the row's own precision.
 *
 * At 0 places the separator never appears at all, so a whole-unit product cannot be
 * given a fractional quantity by accident; above 0 exactly one separator is kept and
 * the tail is cut to the allowed length.
 */
export function sanitizeQtyInput(raw: string, dp: number): string {
  const digitsOnly = raw.replace(/[^0-9.]/g, '');
  if (dp <= 0) return digitsOnly.replace(/\./g, '');
  const firstDot = digitsOnly.indexOf('.');
  if (firstDot < 0) return digitsOnly;
  const whole = digitsOnly.slice(0, firstDot);
  const frac = digitsOnly.slice(firstDot + 1).replace(/\./g, '').slice(0, dp);
  return `${whole}.${frac}`;
}

/** The short hint under the field. One line, no teaching prose. */
export function precisionHint(dp: number, uom: string | null | undefined): string {
  const unit = uom ? ` (${uom})` : '';
  if (dp <= 0) return `Whole units only${unit}`;
  return `Up to ${dp} decimal place${dp === 1 ? '' : 's'}${unit}`;
}

/**
 * The refusal message, worded as the backend's 422 words it, so the same sentence
 * appears whichever side catches it first.
 */
export function precisionError(dp: number, uom: string | null | undefined): string {
  const unit = uom ? ` for ${uom}` : '';
  if (dp <= 0) return `Whole units only${unit}. Remove the decimals.`;
  return `Up to ${dp} decimal place${dp === 1 ? '' : 's'}${unit}.`;
}

/** True when the typed quantity is finer than the frozen snapshot permits. */
export function exceedsPrecision(text: string, dp: number): boolean {
  return decimalsIn(text) > dp;
}

/** A quantity rendered at its own precision. Defined in `lib/format.ts` (the one home
 * for formatters); re-exported here so the precision helpers stay one import. */
export { fmtQty } from '../../lib/format';
