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
    onSuccess: (result) => {
      const total = result.rebound.lines + result.rebound.packing_rows;
      toast.success(
        total > 0 ? `Translation saved, ${total} row${total === 1 ? '' : 's'} updated` : 'Translation saved',
      );
      void qc.invalidateQueries({ queryKey: proformaInvoiceDetailQueryKey(invoiceId) });
      void qc.invalidateQueries({ queryKey: proformaInvoicePackingQueryKey(invoiceId) });
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
