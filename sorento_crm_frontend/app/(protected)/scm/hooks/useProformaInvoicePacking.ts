'use client';

import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  attachPackingListMock,
  dismissPackingLine,
  getProformaInvoicePacking,
  markPackingLineMatched,
  undoDismissPackingLine,
  type ProformaInvoicePackingState,
} from '../proforma-invoices/services/proformaInvoicePackingService';
import type { ProformaInvoiceDetail } from '../services/proformaInvoiceService';

const KEY = ['scm', 'proforma-invoices', 'packing'] as const;

/** The invoice's packing rows and filed packing list (S2, AC-B9/B10) - reads off the
 *  ALREADY-fetched invoice detail (`useProformaInvoice`), never a second network call. */
export function useProformaInvoicePacking(invoice: ProformaInvoiceDetail | undefined) {
  return useQuery<ProformaInvoicePackingState>({
    queryKey: [...KEY, invoice?.id ?? null],
    queryFn: () => getProformaInvoicePacking(invoice as ProformaInvoiceDetail),
    enabled: !!invoice,
  });
}

/** Dismiss / undo / attach all invalidate the SAME cache key their reader watches, so the
 *  Packing tab, the Packed column and the convert dialog stay in step with each other. */
export function useProformaInvoicePackingMutations(invoiceId: string | undefined) {
  const qc = useQueryClient();
  const invalidate = () => void qc.invalidateQueries({ queryKey: [...KEY, invoiceId ?? null] });
  return {
    dismiss: (rowId: string) => {
      if (!invoiceId) return;
      dismissPackingLine(invoiceId, rowId);
      invalidate();
    },
    undoDismiss: (rowId: string) => {
      if (!invoiceId) return;
      undoDismissPackingLine(invoiceId, rowId);
      invalidate();
    },
    /** `MatchToProductDialog`'s own `onMatched` (AC-B12) - the real write is
     *  `useMatchSupplierCode`, unchanged; this only flips the row's own mock
     *  `match_state` so the Packing tab reflects it without a second fetch. */
    match: (rowId: string) => {
      if (!invoiceId) return;
      markPackingLineMatched(invoiceId, rowId);
      invalidate();
    },
    attach: (invoice: ProformaInvoiceDetail) => {
      attachPackingListMock(invoice);
      invalidate();
    },
  };
}
