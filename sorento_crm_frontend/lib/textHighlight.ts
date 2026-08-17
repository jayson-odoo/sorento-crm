/**
 * Splitting text around a user-supplied search term, for `<mark>` rendering.
 *
 * The term comes straight from a search box, so it is NOT a safe regex source:
 * a lone `(` or `*` would throw, and `.` would match every character. It is
 * escaped before it ever reaches `RegExp`.
 */

export type HighlightSegment = { text: string; match: boolean };

/** Escape every character that means something to `RegExp`. */
export function escapeRegExp(input: string): string {
  return input.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * `text` split into alternating plain and matched segments (case-insensitive).
 * An empty term yields one non-matching segment, so callers can render the
 * result unconditionally.
 */
export function splitHighlightSegments(text: string, term: string): HighlightSegment[] {
  const needle = (term ?? '').trim();
  if (!text) return [];
  if (!needle) return [{ text, match: false }];

  const pattern = new RegExp(escapeRegExp(needle), 'gi');
  const out: HighlightSegment[] = [];
  let cursor = 0;
  for (const found of text.matchAll(pattern)) {
    const start = found.index ?? 0;
    if (start > cursor) out.push({ text: text.slice(cursor, start), match: false });
    out.push({ text: found[0], match: true });
    cursor = start + found[0].length;
  }
  if (cursor < text.length) out.push({ text: text.slice(cursor), match: false });
  return out;
}
