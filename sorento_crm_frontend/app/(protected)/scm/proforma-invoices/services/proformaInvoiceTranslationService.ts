/**
 * ============================================================================
 * PI description translations - feature service (S2, text glossary lane)
 * ============================================================================
 * Layering: DescriptionEnCell -> useProformaInvoiceTranslation -> THIS service
 * -> lib/api-client -> backend.
 *
 * ── BACKEND CONTRACT (app/api/v1/scm/proforma_invoices.py) ─────────────────────────────
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
 *  on file whose `description` matches, this PI's rows included (R4 in the plan) - the
 *  `rebound` counts in the response are over EVERY PI on file, not just this one.
 *
 *  `description_en` itself travels on the invoice detail payload's own `lines` /
 *  `packing_lines` (S1 landed) - this file owns only the write path.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export interface ProformaInvoiceTranslationResult {
  source_text: string;
  target_text: string;
  source: 'manual';
  /** Every PI on file just re-bound, not only this invoice's rows (R4). */
  rebound: { lines: number; packing_rows: number };
}

/**
 * Learn one word (R2: inline edit on a row, or System Management > Translations).
 */
export async function upsertProformaInvoiceTranslation(
  invoiceId: string,
  body: { source_text: string; target_text: string },
): Promise<ProformaInvoiceTranslationResult> {
  const res = await apiFetch(`/api/v1/scm/proforma-invoices/${encodeURIComponent(invoiceId)}/translations`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to save this translation'));
  return (await res.json()) as ProformaInvoiceTranslationResult;
}
