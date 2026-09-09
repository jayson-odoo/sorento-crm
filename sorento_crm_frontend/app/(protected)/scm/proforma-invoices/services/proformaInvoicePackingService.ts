/**
 * ============================================================================
 * Supplier packing rows on the invoice - feature service (S2)
 * ============================================================================
 * Layering: ProformaInvoicePackingTab / ProformaInvoiceDetail's Lines tab (Packed column)
 * -> THIS service -> lib/api-client -> backend.
 *
 * ── PHASE-1 / PHASE-2 SWAP ──────────────────────────────────────────────────
 * `USE_PACKING_LINE_MOCKS` is the single flag toggling this feature between the
 * deterministic prototype store (`lib/packingLineMock.ts`, seeded from the invoice's OWN
 * already-real lines so every state - empty, fully matched, mismatched, unmatched,
 * dismissed - is demonstrable against real invoices) and the live backend. Phase 1 = true
 * (no backend). Phase 2 flips it to false; every branch below already has its real
 * `apiFetch` counterpart wired to the contract, so the swap is one line + deleting the
 * mock import.
 *
 * ── PHASE-2 BACKEND CONTRACT (app/api/v1/scm/proforma_invoices.py) ─────────────────────
 *
 *  `GET /api/v1/scm/proforma-invoices/{id}` gains `packing_lines: ProformaInvoicePackingLine[]`
 *    and `packing_file: ProformaInvoicePackingFile | null` (this service reads them off
 *    the SAME detail payload `useProformaInvoices.ts` already fetches - no second GET).
 *  POST   /api/v1/scm/proforma-invoices/{id}/packing-lines/{row_id}/dismiss   -> 200
 *  DELETE /api/v1/scm/proforma-invoices/{id}/packing-lines/{row_id}/dismiss   -> 200 (undo,
 *    within the pending window)
 *    Both gated `scm.proforma_invoice.upload` (AC-B7). Dismiss calls the existing
 *    `supplier_code_alias_service.dismiss`; undo restores `unmatched`.
 *  POST   /api/v1/scm/proforma-invoices/{id}/packing-lines/{row_id}/match    -> 200
 *    Body: the same shape `MatchToProductDialog`'s `useMatchSupplierCode` already sends
 *    (`{ supplier_id, supplier_code, product_id? | product_set_id? }`) - AC-B12 reuses
 *    that mutation directly rather than a second one, so THIS file has no `match`
 *    function of its own; only the mock store update the dialog's `onMatched` calls.
 *
 * `unmapped_headers` on the upload preview (S5, AC-E2) and the dialog's `attach_to` /
 * `refusal` (AC-B5/B13) are documented in `fulfilmentService.ts`, not here.
 * ============================================================================
 */
import {
  getMockPackingState,
  mockAttachPackingList,
  mockSetMatchState,
  packedQtyForLine,
  rollupForLine,
} from '../lib/packingLineMock';
import type { ProformaInvoiceDetail } from '../../services/proformaInvoiceService';
import type {
  ProformaInvoicePackingFile,
  ProformaInvoicePackingLine,
} from '../types/packingLine.types';

export type { ProformaInvoicePackingFile, ProformaInvoicePackingLine };

/** Phase-1 flag - true = deterministic mock store, false = live backend. */
export const USE_PACKING_LINE_MOCKS = true;

export interface ProformaInvoicePackingState {
  rows: ProformaInvoicePackingLine[];
  file: ProformaInvoicePackingFile | null;
}

/** Reads off the ALREADY-fetched invoice detail - no second GET, mock or real: Phase 2's
 *  `packing_lines`/`packing_file` travel on the same detail payload. */
export function getProformaInvoicePacking(invoice: ProformaInvoiceDetail): ProformaInvoicePackingState {
  if (USE_PACKING_LINE_MOCKS) return getMockPackingState(invoice);
  const withPacking = invoice as ProformaInvoiceDetail & {
    packing_lines?: ProformaInvoicePackingLine[];
    packing_file?: ProformaInvoicePackingFile | null;
  };
  return { rows: withPacking.packing_lines ?? [], file: withPacking.packing_file ?? null };
}

export function dismissPackingLine(invoiceId: string, rowId: string): void {
  if (USE_PACKING_LINE_MOCKS) {
    mockSetMatchState(invoiceId, rowId, 'dismissed');
    return;
  }
  // Phase 2: POST .../packing-lines/{row_id}/dismiss
}

export function undoDismissPackingLine(invoiceId: string, rowId: string): void {
  if (USE_PACKING_LINE_MOCKS) {
    mockSetMatchState(invoiceId, rowId, 'unmatched');
    return;
  }
  // Phase 2: DELETE .../packing-lines/{row_id}/dismiss
}

/** `MatchToProductDialog`'s `onMatched` (AC-B12) - the real write is
 *  `useMatchSupplierCode` (unchanged); this flips the row's OWN mock `match_state` so the
 *  Packing tab reflects the pick without a second fetch. Phase 2 needs nothing here: the
 *  real `packing_lines` array on the detail payload already carries the server's answer. */
export function markPackingLineMatched(invoiceId: string, rowId: string): void {
  if (USE_PACKING_LINE_MOCKS) mockSetMatchState(invoiceId, rowId, 'matched');
}

/** "Attach packing list" from an empty PI (AC-B10) - Phase 1 stands in for what a real
 *  upload+apply would do, since no file is genuinely parsed client-side. */
export function attachPackingListMock(invoice: ProformaInvoiceDetail): void {
  mockAttachPackingList(invoice);
}

export { packedQtyForLine, rollupForLine };
