'use client';

import { useCallback } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  bulkDeleteProformaInvoices,
  convertProformaInvoicesToDraftShipment,
  deleteProformaInvoice,
  deleteProformaInvoiceLine,
  getProformaInvoice,
  listDraftShipments,
  listProformaInvoices,
  markProformaInvoiceAsRevisionOf,
  updateProformaInvoice,
  updateProformaInvoiceLine,
  type ConvertOptions,
  type ListProformaInvoicesOptions,
  type ProformaInvoiceDetail,
  type ProformaPlacement,
} from '../services/proformaInvoiceService';

const KEY = ['scm', 'proforma-invoices'] as const;

export function useProformaInvoices(
  supplierId: string | null,
  opts: { limit?: number; offset?: number; placement?: ProformaPlacement | null } = {},
) {
  const options: ListProformaInvoicesOptions = { supplierId, ...opts };
  return useQuery({
    queryKey: [
      ...KEY,
      'list',
      supplierId,
      opts.placement ?? 'all',
      opts.limit ?? 25,
      opts.offset ?? 0,
    ],
    queryFn: () => listProformaInvoices(options),
    refetchOnWindowFocus: false,
  });
}

/** The draft packing lists a convert can be added to instead of creating a new one. */
export function useDraftShipments(supplierId: string | null, enabled = true) {
  return useQuery({
    queryKey: [...KEY, 'draft-shipments', supplierId],
    queryFn: () => listDraftShipments(supplierId),
    enabled,
    refetchOnWindowFocus: false,
  });
}

export function useProformaInvoice(id: string | null) {
  return useQuery({
    queryKey: [...KEY, 'detail', id],
    queryFn: () => getProformaInvoice(id as string),
    enabled: !!id,
    refetchOnWindowFocus: false,
  });
}

/** Invalidate every proforma-invoice list, so a fresh upload shows up wherever it is being
 *  read - the upload dialog does not know which supplier filter the list is currently on. */
export function useProformaInvoicesApplied() {
  const qc = useQueryClient();
  // Stable across renders, so a caller can put it in a `useEffect`/`useCallback` dependency
  // list (e.g. the upload dialog's `onApplied`) without a fresh closure re-triggering it
  // every render.
  return useCallback(() => {
    void qc.invalidateQueries({ queryKey: [...KEY, 'list'] });
  }, [qc]);
}

/**
 * No success toast here: this mutation is used behind `ConfirmDeleteDialog`, which already
 * shows one on success (`successMessage`) - the same split `useDeletePolicy` / `useDeleteTopic`
 * use elsewhere in this module, so a delete never announces itself twice.
 */
export function useDeleteProformaInvoice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteProformaInvoice(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...KEY, 'list'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

/** Same "no success toast here" shape as the single delete above - the caller's own
 *  AlertDialog reports the outcome (deleted count + any blocked/converted invoices). */
export function useBulkDeleteProformaInvoices() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => bulkDeleteProformaInvoices(ids),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...KEY, 'list'] });
    },
  });
}

/**
 * The three writes that adjust ONE invoice to fit the container (AC-E1, AC-E2, AC-D4).
 *
 * Each returns the whole invoice, so the detail cache is SEEDED with the server's answer
 * rather than invalidated and re-fetched: the fill bar, the totals and the was/now figures
 * all move together on save, and a refetch would repaint them one render later. The list is
 * still invalidated, because the line count and the volume it shows have just changed.
 */
function useInvoiceWrite<TArgs>(
  invoiceId: string,
  fn: (args: TArgs) => Promise<ProformaInvoiceDetail>,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (invoice) => {
      qc.setQueryData([...KEY, 'detail', invoiceId], invoice);
      void qc.invalidateQueries({ queryKey: [...KEY, 'list'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useUpdateProformaInvoiceLine(invoiceId: string) {
  return useInvoiceWrite<{ lineId: string; qty: number }>(invoiceId, ({ lineId, qty }) =>
    updateProformaInvoiceLine(invoiceId, lineId, qty),
  );
}

export function useDeleteProformaInvoiceLine(invoiceId: string) {
  return useInvoiceWrite<string>(invoiceId, (lineId) =>
    deleteProformaInvoiceLine(invoiceId, lineId),
  );
}

/** Link a PI uploaded as new to the document it actually revises (AC-E11). */
export function useMarkProformaInvoiceAsRevision(invoiceId: string) {
  return useInvoiceWrite<string>(invoiceId, (previousId) =>
    markProformaInvoiceAsRevisionOf(invoiceId, previousId),
  );
}

export function useUpdateProformaInvoice(invoiceId: string) {
  return useInvoiceWrite<{ container_size_id: string | null }>(invoiceId, (body) =>
    updateProformaInvoice(invoiceId, body),
  );
}

/** Draft a shipment from one or more selected invoices. Invalidates both the proforma list
 *  (their trail now shows where they went) and the invoice detail (converted_shipments +
 *  per-line shipment_number) for every invoice just converted. The caller navigates to
 *  `/scm/incoming` on success - this hook only owns the write + cache invalidation. */
export function useConvertProformaInvoicesToDraftShipment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: {
      invoiceIds: string[];
      overrideReason?: string;
      lineQuantities?: Record<string, number>;
      targetShipmentId?: string | null;
    }) =>
      convertProformaInvoicesToDraftShipment(args.invoiceIds, {
        lineQuantities: args.lineQuantities,
        targetShipmentId: args.targetShipmentId,
        override: args.overrideReason ? { reason: args.overrideReason } : undefined,
      } as ConvertOptions),
    onSuccess: (result) => {
      void qc.invalidateQueries({ queryKey: [...KEY, 'list'] });
      result.invoices.forEach((inv) => {
        void qc.invalidateQueries({ queryKey: [...KEY, 'detail', inv.id] });
      });
    },
  });
}
