/**
 * ============================================================================
 * UOM `decimal_places` - MOCK STORE (Phase 1 only)
 * ============================================================================
 * `decimal_places` is canonical UOM divisibility (plan section 6.4, AC-F12): how
 * finely a unit can be counted, `0..4`, owned by the unit of measure and NOT by
 * SCM. It is not inferred from `conversion_factor` and it is not a planning knob.
 *
 * Slice S2-BE-1 adds the column, its `0..4` validation, the name-based backfill and
 * the field on create / update / list / detail / select. Until then this store
 * answers for it so the master-data screens can be walked:
 *
 *   - reads overlay a value onto the real payload - the session value if the unit
 *     has been edited in this tab, else the NAME class the backfill will use (count
 *     names 0, measure names 3, everything else 0, and the CODE is never consulted,
 *     so `EA` named `Kilogram` is a measure unit);
 *   - writes remember the value here and STRIP it from the request, because the
 *     backend has no column for it yet and would reject or ignore the field.
 *
 * Phase 2 flips `USE_UOM_DECIMAL_PLACES_MOCKS` to false and DELETES this file. The
 * form, the grid and the detail page keep reading `decimal_places` and keep sending
 * it, so none of them changes.
 * ============================================================================
 */
import type { UnitOfMeasure } from '../types/uom.types';

/** Phase-1 flag. Phase 2 sets this false and deletes the file. */
export const USE_UOM_DECIMAL_PLACES_MOCKS = true;

/** The rollout fallback for a unit with no value: whole units. */
export const DEFAULT_UOM_DECIMAL_PLACES = 0;

/**
 * Exact COUNT names, from the plan's backfill list. A count unit is indivisible,
 * so it takes 0 places and `2.5` of it is refused.
 */
const COUNT_NAMES = new Set([
  'ea', 'each', 'piece', 'pieces', 'unit', 'units', 'pc', 'pcs', 'set', 'sets',
]);

/**
 * Exact MEASURE names, from the plan's backfill list. The real backfill gives each
 * one the greatest fractional scale actually observed in the transaction columns,
 * capped at 4; with no database to measure, the mock uses 3 - the case AC-F12 pins
 * (`kg` at three places accepts `2.5`).
 */
const MEASURE_NAMES = new Set([
  'kg', 'kilogram', 'kilograms', 'g', 'gram', 'grams',
  'm', 'meter', 'meters', 'metre', 'metres',
  'cm', 'centimeter', 'centimeters', 'centimetre', 'centimetres',
  'l', 'liter', 'liters', 'litre', 'litres',
  'ml', 'milliliter', 'milliliters', 'millilitre', 'millilitres',
  'm2', 'm²', 'square meter', 'square meters', 'square metre', 'square metres',
  'm3', 'm³', 'cubic meter', 'cubic meters', 'cubic metre', 'cubic metres',
]);

/** The value chosen for a unit in this browser session. Dies with the tab. */
const sessionValues = new Map<string, number>();

/** Drop every session value. Used by tests to keep cases independent. */
export function resetMockDecimalPlaces(): void {
  sessionValues.clear();
}

/**
 * What the backfill would give this unit, from its NAME only.
 *
 * The code is deliberately never consulted: the plan is explicit that a unit coded
 * `EA` but named `Kilogram` is a measure unit, and reading the code would get that
 * backwards for exactly the units it matters for.
 */
export function decimalPlacesFromName(name: string | null | undefined): number {
  const key = (name ?? '').trim().toLowerCase();
  if (COUNT_NAMES.has(key)) return 0;
  if (MEASURE_NAMES.has(key)) return 3;
  return DEFAULT_UOM_DECIMAL_PLACES;
}

/** Overlay the field onto one unit read back from the API. */
export function withDecimalPlaces<T extends UnitOfMeasure>(uom: T): T {
  if (!USE_UOM_DECIMAL_PLACES_MOCKS) return uom;
  const stored = uom.decimal_places;
  if (stored !== null && stored !== undefined) return uom;
  const session = sessionValues.get(uom.id);
  return {
    ...uom,
    decimal_places: session ?? decimalPlacesFromName(uom.uom_name),
  };
}

/** Overlay the field onto a page of units. */
export function withDecimalPlacesList<T extends UnitOfMeasure>(rows: T[]): T[] {
  if (!USE_UOM_DECIMAL_PLACES_MOCKS) return rows;
  return rows.map((r) => withDecimalPlaces(r));
}

/** Remember what a save chose, so the list and detail come back showing it. */
export function rememberDecimalPlaces(id: string, value: number | null | undefined): void {
  if (value === null || value === undefined) return;
  sessionValues.set(id, value);
}

/** The request body without the field the backend has no column for yet. */
export function stripDecimalPlaces<T extends { decimal_places?: number | null }>(
  data: T,
): Omit<T, 'decimal_places'> {
  const rest = { ...data };
  delete (rest as { decimal_places?: number | null }).decimal_places;
  return rest;
}
