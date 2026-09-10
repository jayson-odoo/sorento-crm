'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  getProformaInvoicePacking,
  undoDismissPackingLine,
  type ProformaInvoicePackingState,
} from '../proforma-invoices/services/proformaInvoicePackingService';
import { proformaInvoiceDetailQueryKey } from './useProformaInvoices';
import type { ProformaInvoiceDetail } from '../services/proformaInvoiceService';

const KEY = ['scm', 'proforma-invoices', 'packing'] as const;

export function proformaInvoicePackingQueryKey(invoiceId: string | null) {
  return [...KEY, invoiceId] as const;
}

/** The invoice's packing rows and filed packing list (S2, AC-B9/B10) - reads off the
 *  ALREADY-fetched invoice detail (`useProformaInvoice`), never a second network call.
 *
 *  The `queryFn` reads the detail query's CACHE at call time (`qc.getQueryData`), not the
 *  `invoice` argument's closure: `invoice` is whatever `ProformaInvoiceDetail`/the Packing
 *  tab last rendered with, and a caller that invalidates the detail key and this key
 *  together (`useProformaInvoiceTranslation`'s save) can have this queryFn re-run before
 *  React has re-rendered the parent with the freshly-fetched detail - the closure would
 *  then derive from the STALE `invoice`, mark itself fresh, and never self-correct (a
 *  further invalidate does not refetch an already-fresh query). Reading the cache instead
 *  is correct regardless of render timing, since `setQueryData` on the detail key always
 *  lands before this queryFn is asked to run again (Phase 3 evidence, AC-E2 defect). */
export function useProformaInvoicePacking(invoice: ProformaInvoiceDetail | undefined) {
  const qc = useQueryClient();
  return useQuery<ProformaInvoicePackingState>({
    queryKey: proformaInvoicePackingQueryKey(invoice?.id ?? null),
    queryFn: () => {
      const current =
        (invoice && qc.getQueryData<ProformaInvoiceDetail>(proformaInvoiceDetailQueryKey(invoice.id))) ||
        (invoice as ProformaInvoiceDetail);
      return getProformaInvoicePacking(current);
    },
    enabled: !!invoice,
  });
}

/**
 * The writes the Packing tab makes, and the refetch every one of them needs.
 *
 * Dismiss is NOT here: it parks `proforma_invoice_packing_line.dismiss` as a pending
 * action (`useDeferredRowAction`, AC-B12) and the server applies it when the window
 * lapses. What is here is the two writes with no window - Undo dismiss on an
 * already-dismissed row, and the refresh after a match or an upload - each seeding the
 * detail cache with what the server returned (the same convention `useInvoiceWrite` uses)
 * so the Packed column and the row's own state move together on one render.
 */
export function useProformaInvoicePackingMutations(invoiceId: string | undefined) {
  const qc = useQueryClient();
  const invalidate = () =>
    void qc.invalidateQueries({ queryKey: proformaInvoicePackingQueryKey(invoiceId ?? null) });
  const seedDetail = (invoice: ProformaInvoiceDetail | void) => {
    if (invoice) qc.setQueryData(proformaInvoiceDetailQueryKey(invoiceId ?? null), invoice);
    invalidate();
  };

  const undoDismissMutation = useMutation({
    mutationFn: (rowId: string) => undoDismissPackingLine(invoiceId as string, rowId),
    onSuccess: seedDetail,
    onError: (e: Error) => toast.error(e.message),
  });

  return {
    undoDismiss: (rowId: string) => {
      if (!invoiceId) return;
      undoDismissMutation.mutate(rowId);
    },
    /** After a match made through the in-row picker (which writes the alias itself) or an
     *  upload that attached a packing list: re-read the invoice, rows and all. */
    refresh: () => {
      if (!invoiceId) return;
      void qc.invalidateQueries({ queryKey: proformaInvoiceDetailQueryKey(invoiceId) });
      invalidate();
    },
  };
}
