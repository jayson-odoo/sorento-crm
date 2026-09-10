/**
 * ============================================================================
 * Text glossary (S2, text glossary lane) - feature service
 * ============================================================================
 * Layering: TextGlossaryList / TextGlossaryFormDialog -> THIS service ->
 * lib/api-client -> backend.
 *
 * ── BACKEND CONTRACT (PLAN-text-glossary.md "Routes", S1 - not built yet) ──────────────
 *
 *  GET    /api/v1/system/text-glossary?locale=en&q=
 *    Perm: `system.text_glossary.view`. -> 200 TextGlossaryEntry[], ordered by
 *    `source_text`. No pagination - the same shape `import-field-aliases` GET uses,
 *    because a glossary an operator types by hand one word at a time never grows large
 *    enough to need a page control. `q` is `ILIKE` on `source_text` OR `translation`.
 *    `locale` is always sent as `en` from this page (R9 - hidden until a second target
 *    language exists); THIS file never sends anything else.
 *  PUT    /api/v1/system/text-glossary
 *    Perm: `system.text_glossary.edit`. Body `{ source_text, translation }` -> 200
 *    `TextGlossaryEntry & { rebound: { lines: number, packing_rows: number } }` - the
 *    row plus how many PI lines/packing rows on file were just re-bound (R2's ONE write
 *    path, shared with the PI page's inline edit). 200 whether created or overwritten
 *    (upsert) - a second PUT for the same `source_text` updates the same row. 422 on a
 *    blank `source_text` or `translation`.
 *  DELETE /api/v1/system/text-glossary/{id}
 *    Perm: `system.text_glossary.edit`. -> 204. Registered as the deferred action
 *    `text_glossary.forget` (reversible window, same family as
 *    `import_field_alias.forget`) - THIS file's `deleteTextGlossaryEntry` is the
 *    immediate route behind that action, called by `useDeferredRowAction`, never by the
 *    list directly.
 *
 * ── PHASE 1 MOCK ─────────────────────────────────────────────────────────────────────
 * S1 (BE) has not landed. Every function below reads/writes an in-memory, module-level
 * array (R6: no seed rows - it starts empty) so this page's loading / empty / error /
 * success states are all real. It is intentionally a SEPARATE store from
 * `proformaInvoiceTranslationService.ts`'s mock map - the two share one backend table
 * once S1 lands, but wiring the two Phase-1 mocks together is machinery this phase does
 * not need (the UAC exercises each surface on its own, `text-glossary-acceptance-
 * criteria.md` E1-E6).
 * ============================================================================
 */
import type { TextGlossaryEntry, TextGlossaryUpsertBody } from '../types/textGlossary.types';

let mockRows: TextGlossaryEntry[] = [];

function normalize(text: string): string {
  return text.trim().replace(/\s+/g, ' ');
}

function nowIso(): string {
  return new Date().toISOString();
}

export async function listTextGlossary(query?: string): Promise<TextGlossaryEntry[]> {
  const q = (query ?? '').trim().toLowerCase();
  const rows = q
    ? mockRows.filter(
        (r) => r.source_text.toLowerCase().includes(q) || r.translation.toLowerCase().includes(q),
      )
    : mockRows;
  return [...rows].sort((a, b) => a.source_text.localeCompare(b.source_text));
}

export interface TextGlossaryUpsertResult extends TextGlossaryEntry {
  rebound: { lines: number; packing_rows: number };
}

export async function upsertTextGlossaryEntry(
  body: TextGlossaryUpsertBody,
): Promise<TextGlossaryUpsertResult> {
  const sourceText = normalize(body.source_text);
  const translation = body.translation.trim();
  if (!sourceText) throw new Error("Enter the supplier's wording before saving.");
  if (!translation) throw new Error('Enter the English wording before saving.');

  const existing = mockRows.find((r) => r.source_text.toLowerCase() === sourceText.toLowerCase());
  const timestamp = nowIso();
  let row: TextGlossaryEntry;
  if (existing) {
    existing.translation = translation;
    existing.updated_at = timestamp;
    row = existing;
  } else {
    row = {
      id: crypto.randomUUID(),
      source_text: sourceText,
      translation,
      source: 'manual',
      created_by_name: 'You',
      created_at: timestamp,
      updated_at: timestamp,
    };
    mockRows = [...mockRows, row];
  }
  // Phase 1 has no other PI on file to reach - the real route counts rows it actually
  // rebound (PLAN-text-glossary.md "A6").
  return { ...row, rebound: { lines: 0, packing_rows: 0 } };
}

export async function deleteTextGlossaryEntry(id: string): Promise<void> {
  mockRows = mockRows.filter((r) => r.id !== id);
}

/** Test-only: the array is module state and otherwise outlives every test in the file. */
export function __resetMockTextGlossaryForTests(): void {
  mockRows = [];
}
