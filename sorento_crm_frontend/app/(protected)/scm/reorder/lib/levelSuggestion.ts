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
 * Mirrors `app/services/scm/level_suggestion_service.py`, which decides the numbers; this
 * file only turns them into words.
 */

export interface LevelBasis {
  months: { month: string; qty: number }[];
  months_studied: number;
  total_qty: number;
  avg_monthly: number;
  cover_months: number;
  raw_level: number;
  moq: number | null;
  order_multiple: number | null;
  /** The trajectory verdict that shaped the rounding, or null when none was consulted. */
  trend: string | null;
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

const n = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/\.?0+$/, ''));

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
    return `Nothing left this location in the last ${b.months_studied} months, so the suggested level is 0. A level above that is a judgement call the numbers cannot make.`;
  }

  const parts = [
    `Averaged ${n(b.avg_monthly)} a month over the last ${b.months_studied} months; ${n(b.cover_months)} months of cover makes ${n(b.raw_level)}.`,
  ];
  if (b.trend === 'rising') {
    parts.push('Orders are rising, so it rounds up.');
  } else if (b.trend === 'falling' || b.trend === 'quiet') {
    parts.push(b.trend === 'falling' ? 'Orders are falling, so it rounds down.' : 'Orders went quiet, so it rounds down.');
  }
  if (b.moq !== null && s.suggested_level >= b.moq && b.raw_level < b.moq) {
    parts.push(`The supplier's minimum order of ${n(b.moq)} lifts it to ${n(s.suggested_level)}.`);
  } else if (b.order_multiple && s.suggested_level !== Math.ceil(b.raw_level)) {
    parts.push(`Rounded to the supplier's pack of ${n(b.order_multiple)}.`);
  }
  return parts.join(' ');
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
  trend: string | null;
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
      trend: s.basis.trend,
    }));
}
