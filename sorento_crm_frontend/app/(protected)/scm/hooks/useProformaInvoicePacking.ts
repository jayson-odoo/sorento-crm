'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  attachPackingListMock,
  dismissPackingLine,
  getProformaInvoicePacking,
  markPackingLineMatched,
  undoDismissPackingLine,
  USE_PACKING_LINE_MOCKS,
  type ProformaInvoicePackingState,
} from '../proforma-invoices/services/proformaInvoicePackingService';
import { proformaInvoiceDetailQueryKey } from './useProformaInvoices';
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
 *  Packing tab, the Packed column and the convert dialog stay in step with each other.
 *  Dismiss/undo (S2, AC-B7) are real writes now - each returns the whole invoice, and the
 *  detail cache is SEEDED with it (same convention `useInvoiceWrite` uses) rather than
 *  invalidated and re-fetched, so the Packed column and the row's own state move together
 *  on the same render. */
export function useProformaInvoicePackingMutations(invoiceId: string | undefined) {
  const qc = useQueryClient();
  const invalidate = () => void qc.invalidateQueries({ queryKey: [...KEY, invoiceId ?? null] });
  const seedDetail = (invoice: ProformaInvoiceDetail | void) => {
    if (invoice) qc.setQueryData(proformaInvoiceDetailQueryKey(invoiceId ?? null), invoice);
    invalidate();
  };

  const dismissMutation = useMutation({
    mutationFn: (rowId: string) => dismissPackingLine(invoiceId as string, rowId),
    onSuccess: seedDetail,
    onError: (e: Error) => toast.error(e.message),
  });
  const undoDismissMutation = useMutation({
    mutationFn: (rowId: string) => undoDismissPackingLine(invoiceId as string, rowId),
    onSuccess: seedDetail,
    onError: (e: Error) => toast.error(e.message),
  });

  return {
    dismiss: (rowId: string) => {
      if (!invoiceId) return;
      if (USE_PACKING_LINE_MOCKS) {
        dismissPackingLine(invoiceId, rowId);
        invalidate();
        return;
      }
      dismissMutation.mutate(rowId);
    },
    undoDismiss: (rowId: string) => {
      if (!invoiceId) return;
      if (USE_PACKING_LINE_MOCKS) {
        undoDismissPackingLine(invoiceId, rowId);
        invalidate();
        return;
      }
      undoDismissMutation.mutate(rowId);
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
