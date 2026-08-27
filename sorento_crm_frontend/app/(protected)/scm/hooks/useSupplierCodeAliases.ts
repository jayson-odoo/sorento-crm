'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  dismissSupplierCode,
  forgetSupplierCodeMatch,
  listSupplierCodeAliases,
  listUnmatchedSupplierCodes,
  matchSupplierCode,
} from '../services/supplierCodeAliasService';

const KEY = ['scm', 'supplier-code-aliases'] as const;

export function useSupplierCodeAliases(supplierId: string | null) {
  return useQuery({
    queryKey: [...KEY, 'list', supplierId],
    queryFn: () => listSupplierCodeAliases(supplierId as string),
    enabled: !!supplierId,
    refetchOnWindowFocus: false,
  });
}

export function useUnmatchedSupplierCodes(supplierId: string | null) {
  return useQuery({
    queryKey: [...KEY, 'unmatched', supplierId],
    queryFn: () => listUnmatchedSupplierCodes(supplierId as string),
    enabled: !!supplierId,
    refetchOnWindowFocus: false,
  });
}

/**
 * Record what a code means, and let every screen reading those rows catch up.
 *
 * The write RE-BINDS the stock rows and the invoice lines already uploaded under that code,
 * so the loading plan, the container request and the proforma detail are all stale the
 * moment it returns - they are invalidated together rather than each waiting for its own
 * refetch, which is how two screens end up disagreeing about one code.
 */
export function useMatchSupplierCode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: matchSupplierCode,
    onSuccess: (written) => {
      void qc.invalidateQueries({ queryKey: KEY });
      void qc.invalidateQueries({ queryKey: ['scm', 'proforma-invoices'] });
      void qc.invalidateQueries({ queryKey: ['scm', 'fulfilment'] });
      const moved = written.rebound_stock_rows + written.rebound_invoice_lines;
      toast.success(
        moved > 0
          ? `${written.supplier_code} is ${written.product_code}. ${moved} row${
              moved === 1 ? '' : 's'
            } already on file now point at it.`
          : `${written.supplier_code} is ${written.product_code}.`,
      );
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

/**
 * "None of ours." The code stops being asked about, and the rows it was on are unbound.
 *
 * The same invalidations as a match, for the same reason: a dismissal moves the stock rows
 * and the invoice lines too, so every screen reading them is stale the moment it returns.
 */
export function useDismissSupplierCode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: dismissSupplierCode,
    onSuccess: (written) => {
      void qc.invalidateQueries({ queryKey: KEY });
      void qc.invalidateQueries({ queryKey: ['scm', 'proforma-invoices'] });
      void qc.invalidateQueries({ queryKey: ['scm', 'fulfilment'] });
      toast.success(`${written.supplier_code} will not be asked about again.`);
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

/** No success toast: the caller's own ConfirmDeleteDialog reports the outcome. */
export function useForgetSupplierCodeMatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: forgetSupplierCodeMatch,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY });
      void qc.invalidateQueries({ queryKey: ['scm', 'proforma-invoices'] });
      void qc.invalidateQueries({ queryKey: ['scm', 'fulfilment'] });
    },
  });
}
