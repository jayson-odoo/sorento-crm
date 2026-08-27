/**
 * The third suggestion on a plan row (S13f): the reorder level to set back in AutoCount.
 *
 * > "important aspect is the reorder level and reorder quantity, which are set at autocount
 * >  ... the third suggestion is I should suggest the reorder level"
 *
 * The level lives in AutoCount; this system uploads it (S13c) and SUGGESTS a better one.
 * The engine writes only `suggested_level` + its arithmetic - the stored level is the
 * buyer's, and applying a change in AutoCount is the buyer's job. So every sentence here
 * is an ASK ("Set AutoCount level to 24"), never a claim that anything was changed.
 *
 * The number itself is `ADU x lead time + ADU x 14 days of safety` (AC-R11): ADU is what
 * left every warehouse over the last 90 days, divided by 90.
 *
 * Mirrors `app/services/scm/level_suggestion_service.py`, which decides the numbers; this
 * file only turns them into words.
 */
import { fmtTrimmedDecimal } from '../../lib/format';

/**
 * The three terms behind the suggestion (AC-R11), plus the evidence bars.
 *
 *     level = adu x lead_time_days + adu x safety_days
 */
export interface LevelBasis {
  /** Average daily usage: delivery-order quantity over `window_days` / `window_days`. */
  adu: number;
  /** The product's supplier lead time in days. 30 when nobody knows one. */
  lead_time_days: number;
  /** Where that lead time came from: the plan's own supplier, product_suppliers, or the default. */
  lead_time_source?: string | null;
  /** Days of safety stock carried on top of the lead time's demand. 14 today. */
  safety_days: number;
  /** `adu x safety_days`, the safety half of the level. */
  safety_stock: number;
  /** The study window ADU was averaged over. 90 days today. */
  window_days: number;
  /** Units delivered inside that window. Null on a suggestion stored before it existed. */
  window_qty: number | null;
  /** The level before it was rounded up to a whole unit. */
  raw_level: number;
  /** Monthly bars behind the average. Evidence only - the arithmetic reads the window. */
  months: { month: string; qty: number }[];
  no_movement: boolean;
}

export interface LevelSuggestion {
  product_id: string;
  warehouse_id: string | null;
  product_code: string;
  product_name: string;
  warehouse_code: string | null;
  warehouse_name: string | null;
  /** The level stored today, or null when none is set - which is NOT a level of zero. */
  current_level: number | null;
  current_source: string | null;
  suggested_level: number;
  suggested_at: string | null;
  /** The buyer's own figure, recorded BESIDE the engine's - never instead of it (S14).
   *  Null = no amendment; a fresh planning run clears it. */
  amended_level: number | null;
  amended_at: string | null;
  /** AutoCount's own reorder-quantity suggestion. The engine no longer computes one -
   *  the plan orders `level - net` - so this reads null on a fresh suggestion. */
  suggested_quantity: number | null;
  /** AutoCount's own reorder quantity as uploaded, beside the engine's. */
  master_reorder_quantity: number | null;
  basis: LevelBasis;
}

/** The figure the buyer will actually key into AutoCount: their amendment when they made
 *  one, the engine's suggestion otherwise. */
export function effectiveLevel(s: LevelSuggestion): number {
  return s.amended_level ?? s.suggested_level;
}

export interface LevelSuggestionsPayload {
  suggestions: Record<string, LevelSuggestion>;
  count: number;
}

const n = (v: number) => fmtTrimmedDecimal(v, 2);
/** ADU is a fraction of a unit a day on most items, so it needs more places than a level. */
const rate = (v: number) => fmtTrimmedDecimal(v, 3);

/** The row's action, with both numbers: "set to 24" means nothing without "now 20". */
export function levelActionLabel(s: LevelSuggestion): {
  label: string;
  detail: string;
  changed: boolean;
} {
  const target = effectiveLevel(s);
  const amended = s.amended_level !== null && s.amended_level !== s.suggested_level;

  // Suggesting "set it to 0" where none is set asks for a data-entry trip that changes
  // nothing. Not a change - but it still says so, because silence would read as "not
  // computed" rather than "nothing moved".
  if (s.current_level === null && target === 0) {
    return { label: 'No level needed', detail: 'nothing moved', changed: false };
  }
  const changed = s.current_level === null || s.current_level !== target;
  if (!changed) {
    return { label: `Level ${n(target)} still fits`, detail: 'no change needed', changed };
  }
  const now = s.current_level === null ? 'none set today' : `now ${n(s.current_level)}`;
  return {
    label: `Set AutoCount level to ${n(target)}`,
    // The engine's number never disappears behind the amendment: an override the reader
    // cannot compare against its source reads as the engine flip-flopping.
    detail: amended ? `you set this; engine said ${n(s.suggested_level)}, ${now}` : now,
    changed,
  };
}

/** The quantity line under the level: "order 24 when it fires (AutoCount says 18)". */
export function quantityActionLabel(s: LevelSuggestion): string | null {
  if (s.suggested_quantity === null) return null;
  const master = s.master_reorder_quantity;
  const differs = master === null || master !== s.suggested_quantity;
  if (!differs) return `Reorder qty ${n(s.suggested_quantity)} still fits`;
  const now = master === null ? 'none set today' : `now ${n(master)}`;
  return `Reorder qty ${n(s.suggested_quantity)}, ${now}`;
}

/**
 * The arithmetic, in a sentence the buyer can argue with.
 *
 * Every clause names a number that produced the suggestion. A verdict without its sums is
 * the one thing the buyer said they would not trust.
 */
export function describeLevelSuggestion(s: LevelSuggestion | undefined): string {
  if (!s) return 'No level suggestion for this item.';
  const b = s.basis;

  if (b.no_movement) {
    return `Nothing left the warehouses in the last ${n(b.window_days)} days, so the suggested level is 0. A level above that is a judgement call the numbers cannot make.`;
  }

  const parts = [
    b.window_qty !== null
      ? `${n(b.window_qty)} left the warehouses over the last ${n(b.window_days)} days, so ${rate(b.adu)} a day.`
      : `${rate(b.adu)} a day over the last ${n(b.window_days)} days.`,
    `A ${n(b.lead_time_days)} day lead needs ${n(b.adu * b.lead_time_days)}, and ${n(b.safety_days)} days of safety adds ${n(b.safety_stock)}: ${n(b.raw_level)}, rounded up to ${n(s.suggested_level)}.`,
  ];
  if (b.lead_time_source === 'default') {
    parts.push(`No lead time is on file for this product, so ${n(b.lead_time_days)} days stands in.`);
  }
  return parts.join(' ');
}

/** The three terms, each as its own labelled figure - the popover shows them beside the
 *  sentence so the arithmetic can be checked without reading prose. */
export function levelTerms(s: LevelSuggestion): { label: string; value: string }[] {
  const b = s.basis;
  return [
    { label: 'ADU', value: `${rate(b.adu)} / day` },
    { label: 'Lead time', value: `${n(b.lead_time_days)} d` },
    { label: 'Safety', value: `${n(b.safety_stock)} (${n(b.safety_days)} d)` },
  ];
}

/** The key both the plan row and the suggestion map agree on. Warehouse optional. */
export function levelKey(productId: string | null, warehouseId: string | null): string | null {
  if (!productId) return null;
  return `${productId}:${warehouseId ?? ''}`;
}

/** The change list: only rows where the suggestion differs, named the way AutoCount is. */
export function levelRowsForExport(suggestions: Record<string, LevelSuggestion>): {
  product_code: string;
  product_name: string;
  warehouse: string | null;
  current_level: number | null;
  /** The figure to key in: the amendment when one was made, else the engine's. */
  suggested_level: number;
  /** The engine's own figure, only when an amendment displaced it. */
  engine_level: number | null;
  /** The two terms that sized it, so the change list can be argued with in a spreadsheet. */
  adu: number;
  lead_time_days: number;
}[] {
  return Object.values(suggestions)
    .filter((s) => levelActionLabel(s).changed)
    .map((s) => ({
      product_code: s.product_code,
      product_name: s.product_name,
      warehouse: s.warehouse_code,
      current_level: s.current_level,
      suggested_level: effectiveLevel(s),
      engine_level:
        s.amended_level !== null && s.amended_level !== s.suggested_level
          ? s.suggested_level
          : null,
      adu: s.basis.adu,
      lead_time_days: s.basis.lead_time_days,
    }));
}
