/** `scm.proforma_invoice_packing_line.match_state` (S2, AC-B1). */
export type PackingLineMatchState = 'matched' | 'unmatched' | 'dismissed';

/** One supplier packing-list row, verbatim, matched to the invoice line whose product it
 *  is (S2, AC-B1). Company-scoped and timestamped on the real table; the FE shape carries
 *  only what the Packing tab and the convert dialog read. */
export interface ProformaInvoicePackingLine {
  id: string;
  /** Null when the row's product is on no line of this PI (AC-B6, `unmatched_reason:
   *  'not_on_invoice'`) - spares, customs samples, a shared-container note. */
  proforma_invoice_line_id: string | null;
  row_no: number;
  item_code: string;
  supplier_code: string | null;
  description: string | null;
  /** The glossary's English for `description` (S2, text glossary lane) - `null` for a
   *  word the glossary has never seen, even an already-English one (R7). Optional
   *  because the real backend does not send it until S1 lands; `applyMockDescriptionEn`
   *  fills it client-side until then (`proformaInvoiceTranslationService.ts`). */
  description_en?: string | null;
  product_id: string | null;
  product_set_id: string | null;
  qty: number;
  cartons: number | null;
  pcs_per_carton: number | null;
  carton_length_cm: number | null;
  carton_width_cm: number | null;
  carton_height_cm: number | null;
  cbm_per_carton: number | null;
  cbm_total: number | null;
  /** Per carton, as the document states it. */
  net_weight: number | null;
  gross_weight: number | null;
  total_net_weight: number | null;
  total_gross_weight: number | null;
  material: string | null;
  container_no: string | null;
  remark: string | null;
  match_state: PackingLineMatchState;
  /** Set only when `match_state === 'unmatched'`. */
  unmatched_reason: string | null;
}

/** The packing-list file filed against this PI (AC-B10/B14) - the PI's own uploaded
 *  file, never the shipment's. */
export interface ProformaInvoicePackingFile {
  name: string;
  uploaded_at: string;
}
