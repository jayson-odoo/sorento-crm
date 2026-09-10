/**
 * ============================================================================
 * PI description translations - feature service (S2, text glossary lane)
 * ============================================================================
 * Layering: DescriptionEnCell -> useProformaInvoiceTranslation -> THIS service
 * -> lib/api-client -> backend.
 *
 * ── BACKEND CONTRACT (PLAN-text-glossary.md "Route", S1 - not built yet) ───────────────
 *
 *  PUT /api/v1/scm/proforma-invoices/{invoiceId}/translations
 *    Perm: `scm.proforma_invoice.upload` (the same permission that gates Match/Dismiss
 *    on the Packing tab - the person handling the PI names the word).
 *    Body: { source_text: string, target_text: string }
 *    -> 200 { source_text, target_text, source: 'manual', rebound: { lines: number,
 *             packing_rows: number } }
 *    404 when `invoiceId` names no invoice (the route is reachable only from a PI the
 *    caller can already see). 422 on a blank `source_text` or `target_text`.
 *
 *  This is a thin, PI-scoped door onto `translation_service.remember` (R11 - the SAME
 *  write path System Management > Translations' inline edit already uses; there is no
 *  separate glossary table). The write is NOT scoped to this invoice:
 *  `description_translation.rebind` (called from `remember` after its own write) updates
 *  `description_en` on every `proforma_invoice_line` and `proforma_invoice_packing_line`
 *  on file whose `description` matches, this PI's rows included (R4 in the plan).
 *
 * ── PHASE 1 MOCK ─────────────────────────────────────────────────────────────────────
 * S1 (BE) has not landed, so there is no route to call yet. `upsert` below writes into
 * an in-memory, module-level map - normalised source text -> English - that lives for
 * the life of the tab; `applyMockDescriptionEn` decorates whatever rows the Packing tab
 * / Lines tab already fetched from the REAL backend (which has no `description_en`
 * column yet) so both screens show real dash / English / edit behaviour. The mock only
 * ever sees rows already loaded on THIS invoice's detail payload - it cannot reach
 * every other PI on file the way the real `rebind` will, so the "N rows updated" count
 * this phase reports is scoped to the current invoice + its packing rows, not every PI
 * on file. DoD gate item 1 swaps this for the real PUT once S1 lands.
 * ============================================================================
 */

/** Trimmed, internal whitespace collapsed - the same string two differently spaced
 *  cells resolve to, matching `translation_service.normalize_source_text`. */
export function normalizeDescription(text: string | null | undefined): string {
  return (text ?? '').trim().replace(/\s+/g, ' ');
}

/** Phase 1 only: normalised source text -> English. R6 (no seed rows) - starts empty. */
const mockGlossary = new Map<string, string>();

/**
 * Phase 1 only, and load-bearing: the Lines tab decorates `useProformaInvoice`'s ALREADY
 * FETCHED lines with the mock in a plain `useMemo` keyed on `data`. React Query's default
 * structural sharing hands back the SAME `data` reference after a refetch whenever the
 * backend's own JSON is byte-for-byte unchanged - which it always is here, since the mock
 * lives entirely on the client. Without an independent signal, a save would write the map
 * correctly and the Lines tab would still show the dash forever. `useMockGlossaryVersion`
 * (in `useProformaInvoiceTranslation.ts`) subscribes a component to `bump()` below so it
 * re-renders on every write regardless of the query's own referential identity. The
 * Packing tab does not need this - its decoration runs inside a `queryFn`
 * (`getProformaInvoicePacking`), which TanStack always re-invokes on invalidate.
 */
let version = 0;
const listeners = new Set<() => void>();
function bump(): void {
  version += 1;
  for (const listener of listeners) listener();
}
export function subscribeMockGlossary(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
export function getMockGlossaryVersion(): number {
  return version;
}

export interface ProformaInvoiceTranslationResult {
  source_text: string;
  target_text: string;
  source: 'manual';
  /** How many rows on THIS invoice's already-loaded lines + packing rows now read the
   *  new English - the caller (the mutation hook) counts these from its own cache,
   *  since the phase-1 mock has no other PI to reach. */
  rebound: { lines: number; packing_rows: number };
}

/**
 * Learn one word (R2: inline edit on a row, or System Management > Translations). 422-
 * shaped `Error` on a blank `source_text` or `target_text`, matching the real route.
 */
export async function upsertProformaInvoiceTranslation(
  _invoiceId: string,
  body: { source_text: string; target_text: string },
  rebound: { lines: number; packing_rows: number } = { lines: 0, packing_rows: 0 },
): Promise<ProformaInvoiceTranslationResult> {
  const key = normalizeDescription(body.source_text);
  const targetText = body.target_text.trim();
  if (!key) throw new Error('Nothing to translate for this row.');
  if (!targetText) throw new Error('Enter the English wording before saving.');
  mockGlossary.set(key, targetText);
  bump();
  return { source_text: body.source_text, target_text: targetText, source: 'manual', rebound };
}

/** `null` for a description the glossary has never seen (R7: an already-English
 *  description still shows a dash until someone confirms it, never auto-mirrored). */
export function lookupDescriptionEn(description: string | null | undefined): string | null {
  const key = normalizeDescription(description);
  if (!key) return null;
  return mockGlossary.get(key) ?? null;
}

/** Decorates rows that carry a `description` with the mock's `description_en` - the
 *  Packing tab and the Lines tab call this on whatever they already fetched, so a save
 *  that updates the map re-renders every row on screen sharing that description. */
export function applyMockDescriptionEn<T extends { description: string | null }>(
  rows: T[],
): (T & { description_en: string | null })[] {
  return rows.map((row) => ({ ...row, description_en: lookupDescriptionEn(row.description) }));
}

/** Test-only: the map is module state and otherwise outlives every test in the file. */
export function __resetMockGlossaryForTests(): void {
  mockGlossary.clear();
  bump();
}
