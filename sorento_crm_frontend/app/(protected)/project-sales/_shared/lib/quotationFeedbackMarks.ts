/**
 * Customer feedback names the ISSUED version's lines; a revise copies every line under a new id
 * (`copy_line` keeps product_id / product_set_id / sort_order / band_label, and the columns keep
 * their keys). So a note shows on the draft by matching its line there: same product (or set),
 * same occurrence among that product's lines in sort order. PS-QUOTE-MATRIX R20 / E6.
 */
import type { QuotationFeedbackRow, QuotationLine } from '../types/project.types';

type LineLike = Pick<QuotationLine, 'id' | 'product_id' | 'product_set_id' | 'sort_order'>;

function productKey(line: LineLike): string | null {
  if (line.product_set_id) return `set:${line.product_set_id}`;
  if (line.product_id) return `product:${line.product_id}`;
  return null;
}

/** `line id -> "<product key>#<occurrence>"` for one version's lines. */
function slots(lines: LineLike[]): Map<string, string> {
  const seen = new Map<string, number>();
  const out = new Map<string, string>();
  [...lines]
    .sort((a, b) => a.sort_order - b.sort_order)
    .forEach((line) => {
      const key = productKey(line);
      if (!key) return;
      const n = seen.get(key) ?? 0;
      seen.set(key, n + 1);
      out.set(line.id, `${key}#${n}`);
    });
  return out;
}

/**
 * The notes, each pointed at a line of `target` (the version on screen): kept as is when its line
 * is already there, else carried to the line holding the same product slot, matched through the
 * versions in `sources` (each version's lines on its own, since occurrence counts per version).
 * A note whose line cannot be found in `target` is left out: it marks nothing on this version.
 */
export function carryFeedback(
  notes: QuotationFeedbackRow[],
  sources: LineLike[][],
  target: LineLike[],
): QuotationFeedbackRow[] {
  const targetIds = new Set(target.map((line) => line.id));
  const targetBySlot = new Map<string, string>();
  slots(target).forEach((slot, id) => targetBySlot.set(slot, id));
  const sourceSlot = new Map<string, string>();
  sources.forEach((lines) => slots(lines).forEach((slot, id) => sourceSlot.set(id, slot)));

  return notes.flatMap((note) => {
    if (targetIds.has(note.line_id)) return [note];
    const slot = sourceSlot.get(note.line_id);
    const carried = slot ? targetBySlot.get(slot) : undefined;
    return carried ? [{ ...note, line_id: carried }] : [];
  });
}
