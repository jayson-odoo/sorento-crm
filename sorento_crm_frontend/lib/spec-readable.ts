/**
 * Turn a system key into the words a person uses.
 *
 * `dim_height` is what the database calls it and what the n8n parser is held to. It is
 * not what a human calls anything, and it had been leaking onto every screen - a
 * product page listing "dim height" and "seat material" reads like a debug dump.
 *
 * The registry's own `label` is always better where one is to hand ("Height", "Finish
 * or colour"); this is the fallback for the places that only have the key.
 */
const SPECIAL: Record<string, string> = {
  dim_length: 'Length',
  dim_width: 'Width',
  dim_height: 'Height',
  bowl_count: 'Number of bowls',
  is_smart: 'Intelligent / smart',
  has_drainer: 'Drainer board',
  has_overflow: 'Overflow',
  has_fixing_screw: 'Fixing screw',
  seat_material: 'Seat cover material',
  trap_length: 'Trap outlet length',
  trap_type: 'Trap',
  product_type: 'Type',
  control_type: 'Control type',
  spout_type: 'Spout',
  flush_type: 'Flush type',
  class: 'Product class',
  finish: 'Finish or colour',
};

/**
 * `_self` is not a value. It holds the words that name the SPECIFICATION itself - 
 * "bowl", "height", "deep" - as opposed to the words for one of its values. Rendered
 * through the generic path it came out as "Self", which reads like a value nobody can
 * find in the catalogue.
 */
export const SELF_KEY = '_self';

export function readable(key: string): string {
  if (!key) return '';
  if (key === SELF_KEY) return 'Words for the spec itself';
  const known = SPECIAL[key];
  if (known) return known;
  const words = key.replace(/_/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}


/**
 * A stored VALUE as a person reads it: `one_piece` -> "One piece", 770 -> "770 mm".
 *
 * The slug is the shared vocabulary the ranker and the n8n parser agree on, so it has
 * to stay exactly as it is in the data. It just has no business being the thing a
 * human reads off a product page.
 */
export function readableValue(value: unknown, unit?: string): string {
  // A key a product may hold more than one of (a two-tone finish) is stored as a LIST,
  // by derivation and by an accepted proposal alike. Each element is read exactly as a
  // single value would be, so "Rose Gold + Matt Black" comes back as the two words a
  // person recognises rather than as the array Javascript would print.
  if (Array.isArray(value)) {
    return value
      .map((item) => readableValue(item, unit))
      .filter((text) => text !== '')
      .join(', ');
  }
  if (value === true) return 'Yes';
  if (value === false) return 'No';
  if (typeof value === 'number') return unit ? `${value} ${unit}` : String(value);
  const text = String(value ?? '');
  if (!text) return '';
  // Left alone when it is already prose or a code: only slugs get rewritten.
  if (!/^[a-z0-9]+(_[a-z0-9]+)*$/.test(text)) return unit ? `${text} ${unit}` : text;
  const words = text.replace(/_/g, ' ');
  const pretty = words.charAt(0).toUpperCase() + words.slice(1);
  return unit ? `${pretty} ${unit}` : pretty;
}

/**
 * A stored spec ENTRY as a person reads it: `{ value: 'glass' }` -> "Glass",
 * `{ value: 770, unit: 'mm' }` -> "770 mm".
 *
 * `spec.values` stores an entry per key, never a bare scalar, and anything carrying a
 * slice of that JSON straight to the screen carries entries with it - the verification
 * diff (`invalidated_diff.changed[].was/now`) is one such slice. Handing an entry to
 * `readableValue` renders the literal `[object Object]`, which is exactly what the
 * needs-re-verify block did. A bare scalar is still accepted, because a hand-written
 * fixture or an older row is not worth a crash.
 *
 * Returns the empty string for "there was nothing here", so the caller picks its own
 * word for absence ("nothing", a dash) rather than having one imposed.
 */
export function readableEntry(entry: unknown): string {
  if (entry === null || entry === undefined) return '';
  if (typeof entry === 'object') {
    const { value, unit } = entry as { value?: unknown; unit?: unknown };
    if (value === null || value === undefined) return '';
    return readableValue(value, typeof unit === 'string' && unit ? unit : undefined);
  }
  return readableValue(entry);
}
