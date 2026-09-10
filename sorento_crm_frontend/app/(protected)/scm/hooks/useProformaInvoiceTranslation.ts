'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { upsertProformaInvoiceTranslation } from '../proforma-invoices/services/proformaInvoiceTranslationService';
import { proformaInvoiceDetailQueryKey } from './useProformaInvoices';
import { proformaInvoicePackingQueryKey } from './useProformaInvoicePacking';

/**
 * The write behind `DescriptionEnCell` (S2, AC-E2/E3): one word learnt from a Packing-tab
 * or Lines-tab row, re-bound onto every row on file sharing that description (R2/R4).
 * `rebound` in the response is the count across every PI on file, not just this one.
 */
export function useProformaInvoiceTranslationMutation(invoiceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { source_text: string; target_text: string }) =>
      upsertProformaInvoiceTranslation(invoiceId, body),
    onSuccess: async (result) => {
      const total = result.rebound.lines + result.rebound.packing_rows;
      toast.success(
        total > 0 ? `Translation saved, ${total} row${total === 1 ? '' : 's'} updated` : 'Translation saved',
      );
      // Awaited, in this order: the packing query's own `queryFn` reads the detail query's
      // CACHE at call time (`useProformaInvoicePacking`), not a render closure - so it only
      // sees the new English once the detail refetch below has actually landed in that
      // cache. Firing both at once let the packing query refetch first, off the still-old
      // cache, mark itself fresh, and never self-correct (AC-E2 defect, Phase 3 evidence).
      await qc.invalidateQueries({ queryKey: proformaInvoiceDetailQueryKey(invoiceId) });
      await qc.invalidateQueries({ queryKey: proformaInvoicePackingQueryKey(invoiceId) });
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
