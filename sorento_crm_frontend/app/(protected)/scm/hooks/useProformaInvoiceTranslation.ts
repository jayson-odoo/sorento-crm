'use client';

import { useSyncExternalStore } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  getMockGlossaryVersion,
  normalizeDescription,
  subscribeMockGlossary,
  upsertProformaInvoiceTranslation,
} from '../proforma-invoices/services/proformaInvoiceTranslationService';
import { proformaInvoiceDetailQueryKey } from './useProformaInvoices';
import { proformaInvoicePackingQueryKey } from './useProformaInvoicePacking';
import type { ProformaInvoiceDetail } from '../services/proformaInvoiceService';
import type { ProformaInvoicePackingState } from '../proforma-invoices/services/proformaInvoicePackingService';

/**
 * The write behind `DescriptionEnCell` (S2, AC-E2/E3): one word learnt from a Packing-tab
 * or Lines-tab row, re-bound onto every row on file sharing that description (R2/R4).
 *
 * The "N rows updated" count is read off THIS invoice's own cached detail + packing
 * rows before the write - the real route re-binds every PI on file, but the phase-1
 * mock (`proformaInvoiceTranslationService`) can only reach what is already loaded here.
 */
export function useProformaInvoiceTranslationMutation(invoiceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { source_text: string; target_text: string }) => {
      const key = normalizeDescription(body.source_text);
      const invoice = qc.getQueryData<ProformaInvoiceDetail>(
        proformaInvoiceDetailQueryKey(invoiceId),
      );
      const packing = qc.getQueryData<ProformaInvoicePackingState>(
        proformaInvoicePackingQueryKey(invoiceId),
      );
      const lines = (invoice?.lines ?? []).filter(
        (l) => normalizeDescription(l.description) === key,
      ).length;
      const packingRows = (packing?.rows ?? []).filter(
        (r) => normalizeDescription(r.description) === key,
      ).length;
      return upsertProformaInvoiceTranslation(invoiceId, body, {
        lines,
        packing_rows: packingRows,
      });
    },
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

/**
 * Phase 1 only: re-renders the caller on every mock-glossary write, so a component that
 * decorates ALREADY-FETCHED data with `applyMockDescriptionEn` in a plain `useMemo` (the
 * Lines tab) does not depend on the fetch's own referential identity - see the docstring
 * on `subscribeMockGlossary`. Once S1 lands and `description_en` travels on the real
 * payload, this hook and its one caller are deleted with the rest of the mock.
 */
export function useMockGlossaryVersion(): number {
  return useSyncExternalStore(subscribeMockGlossary, getMockGlossaryVersion, getMockGlossaryVersion);
}
