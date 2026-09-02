'use client';

import { useCallback } from 'react';
import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  bulkDeleteProformaInvoices,
  convertProformaInvoicesToDraftShipment,
  getProformaInvoice,
  listProformaInvoices,
  markProformaInvoiceAsRevisionOf,
  saveProformaInvoice,
  type ConvertOptions,
  type ListProformaInvoicesOptions,
  type ProformaInvoiceDetail,
  type ProformaInvoiceWrite,
  type ProformaPlacement,
} from '../services/proformaInvoiceService';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';

const KEY = ['scm', 'proforma-invoices'] as const;

/**
 * The list's React Query key. The detail page's pager rebuilds the SAME key from
 * the URL, so it reads the page the list already fetched.
 *
 * The list endpoint caps `limit` at 100; the list's own page-size control is
 * capped to match (`ProformaInvoicesView`), so the URL can only ever name a size
 * the endpoint accepts and the pager's arithmetic agrees with the fetch.
 */
export function proformaInvoicesListQueryKey(
  options: ListProformaInvoicesOptions,
): QueryKey {
  return [
    ...KEY,
    'list',
    options.supplierId ?? null,
    options.placement ?? 'all',
    options.query ?? '',
    options.limit ?? 25,
    options.offset ?? 0,
  ];
}

/** The list query a detail URL describes, in the shape the list passes. */
export function proformaInvoicesListParamsFromUrl(
  params: ListPagerParams,
): ListProformaInvoicesOptions {
  return {
    supplierId: params.filters.supplier_id || null,
    placement: (params.filters.placement as ProformaPlacement) || null,
    query: params.searchQuery || null,
    limit: params.pageSize,
    offset: params.pageIndex * params.pageSize,
  };
}

/** The pager's two hooks into the proforma invoice list. */
export const proformaInvoicesPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    proformaInvoicesListQueryKey(proformaInvoicesListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    listProformaInvoices(proformaInvoicesListParamsFromUrl(params)),
};

export function useProformaInvoices(
  supplierId: string | null,
  opts: {
    limit?: number;
    offset?: number;
    placement?: ProformaPlacement | null;
    /** The list toolbar's search box: PI number, supplier, container or BL. */
    query?: string | null;
  } = {},
) {
  const options: ListProformaInvoicesOptions = { supplierId, ...opts };
  return useQuery({
    queryKey: proformaInvoicesListQueryKey(options),
    queryFn: () => listProformaInvoices(options),
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

/** No success toast here: the caller's own AlertDialog reports the outcome (deleted
 *  count + any blocked/converted invoices). */
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
 * The writes that change ONE invoice (AC-E1, AC-E2, AC-D4, AC-E11).
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

/** Link a PI uploaded as new to the document it actually revises (AC-E11). */
export function useMarkProformaInvoiceAsRevision(invoiceId: string) {
  return useInvoiceWrite<string>(invoiceId, (previousId) =>
    markProformaInvoiceAsRevisionOf(invoiceId, previousId),
  );
}

/**
 * The edit screen's Save: the number, the container size and the whole line array, together.
 *
 * There is deliberately no per-line hook beside it. The screen holds a DRAFT - a struck-
 * through line is not gone until Save - so a per-line write would have to be replayed in
 * order, and a refusal halfway through would leave the document half-applied under a screen
 * still showing the draft.
 */
export function useSaveProformaInvoice(invoiceId: string) {
  return useInvoiceWrite<ProformaInvoiceWrite>(invoiceId, (body) =>
    saveProformaInvoice(invoiceId, body),
  );
}

/** Turn one or more selected invoices into ONE NEW draft packing list. Invalidates both the proforma list
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
    }) =>
      convertProformaInvoicesToDraftShipment(args.invoiceIds, {
        lineQuantities: args.lineQuantities,
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
