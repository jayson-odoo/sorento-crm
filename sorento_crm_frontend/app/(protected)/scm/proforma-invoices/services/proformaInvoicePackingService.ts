/**
 * ============================================================================
 * Supplier packing rows on the invoice - feature service (S2)
 * ============================================================================
 * Layering: ProformaInvoicePackingTab / ProformaInvoiceDetail's Lines tab (Packed column)
 * -> THIS service -> lib/api-client -> backend.
 *
 * ── BACKEND CONTRACT (app/api/v1/scm/proforma_invoices.py) ────────────────────────────
 *
 *  `GET /api/v1/scm/proforma-invoices/{id}` carries `packing_lines: ProformaInvoicePackingLine[]`
 *    and `packing_file: ProformaInvoicePackingFile | null` - read off the SAME detail
 *    payload `useProformaInvoices.ts` already fetches, never a second GET.
 *  POST   /api/v1/scm/proforma-invoices/{id}/packing-lines/{row_id}/dismiss   -> 200
 *  DELETE /api/v1/scm/proforma-invoices/{id}/packing-lines/{row_id}/dismiss   -> 200 (undo
 *    of an already-dismissed row, from its own gear)
 *  POST   /api/v1/scm/proforma-invoices/{id}/packing-lines/{row_id}/match     -> 200
 *    Body `{product_id?, product_set_id?}`. All three gated `scm.proforma_invoice.upload`.
 *
 * The row's Dismiss does NOT call the POST above directly: it parks
 * `proforma_invoice_packing_line.dismiss` as a pending action (`useDeferredRowAction`,
 * AC-B12) and the server applies it when the window lapses. The function stays here as the
 * immediate route behind that action.
 *
 * `unmapped_headers` on the upload preview (S5, AC-E2) and the dialog's per-block
 * `attach_to` / `refusal` (AC-B5/B13) are documented in `fulfilmentService.ts`, not here.
 *
 * `description_en` on each row (S2, text glossary lane) travels on `packing_lines` itself
 * - `proformaInvoiceTranslationService.ts` owns the write path that fills it.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import { packedQtyForLine } from '../lib/packingRollup';
import type { ProformaInvoiceDetail } from '../../services/proformaInvoiceService';
import type {
  ProformaInvoicePackingFile,
  ProformaInvoicePackingLine,
} from '../types/packingLine.types';

export type { ProformaInvoicePackingFile, ProformaInvoicePackingLine };

export interface ProformaInvoicePackingState {
  rows: ProformaInvoicePackingLine[];
  file: ProformaInvoicePackingFile | null;
}

/** Reads off the ALREADY-fetched invoice detail - no second GET: `packing_lines` and
 *  `packing_file` travel on the same detail payload. */
export function getProformaInvoicePacking(invoice: ProformaInvoiceDetail): ProformaInvoicePackingState {
  const withPacking = invoice as ProformaInvoiceDetail & {
    packing_lines?: ProformaInvoicePackingLine[];
    packing_file?: ProformaInvoicePackingFile | null;
  };
  return { rows: withPacking.packing_lines ?? [], file: withPacking.packing_file ?? null };
}

export async function dismissPackingLine(
  invoiceId: string,
  rowId: string,
): Promise<ProformaInvoiceDetail> {
  const res = await apiFetch(
    `/api/v1/scm/proforma-invoices/${invoiceId}/packing-lines/${rowId}/dismiss`,
    { method: 'POST' },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to dismiss this row'));
  return (await res.json()) as ProformaInvoiceDetail;
}

export async function undoDismissPackingLine(
  invoiceId: string,
  rowId: string,
): Promise<ProformaInvoiceDetail> {
  const res = await apiFetch(
    `/api/v1/scm/proforma-invoices/${invoiceId}/packing-lines/${rowId}/dismiss`,
    { method: 'DELETE' },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to undo the dismissal'));
  return (await res.json()) as ProformaInvoiceDetail;
}

/**
 * "It is this product after all" on a packing row (AC-B12). The in-row picker
 * (`MatchToProductDialog`) writes the supplier's manual alias itself through
 * `useMatchSupplierCode`, which is what rebinds the row and re-rolls its line; this route
 * is the same decision made in one call, for a caller that holds the row rather than the
 * dialog.
 */
export async function matchPackingLine(
  invoiceId: string,
  rowId: string,
  body: { product_id?: string; product_set_id?: string },
): Promise<ProformaInvoiceDetail> {
  const res = await apiFetch(
    `/api/v1/scm/proforma-invoices/${invoiceId}/packing-lines/${rowId}/match`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to match this row'));
  return (await res.json()) as ProformaInvoiceDetail;
}

export { packedQtyForLine };
