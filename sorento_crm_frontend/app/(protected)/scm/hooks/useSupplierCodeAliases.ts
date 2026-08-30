'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  dismissSupplierCode,
  listSupplierCodeAliases,
  listUnmatchedSupplierCodes,
  matchSupplierCode,
  rematchSupplierCodes,
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
      // A set ruling names no product, so the sentence has to read off whichever half the
      // answer actually filled in - "is null" was the alternative.
      const named = written.set_code
        ? `set ${written.set_code}`
        : (written.product_code ?? 'that product');
      toast.success(
        moved > 0
          ? `${written.supplier_code} is ${named}. ${moved} row${
              moved === 1 ? '' : 's'
            } already on file now point at it.`
          : `${written.supplier_code} is ${named}.`,
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

/**
 * Run the ladder again over the rows still unbound, after master data has moved.
 *
 * The same invalidations as a match: it binds stock rows and invoice lines, so the loading
 * plan, the container request and the proforma screens are stale the moment it returns. The
 * toast says what moved and what is left, because the button is otherwise indistinguishable
 * from one that did nothing.
 */
export function useRematchSupplierCodes() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: rematchSupplierCodes,
    onSuccess: (out) => {
      void qc.invalidateQueries({ queryKey: KEY });
      void qc.invalidateQueries({ queryKey: ['scm', 'proforma-invoices'] });
      void qc.invalidateQueries({ queryKey: ['scm', 'fulfilment'] });
      const bound = out.inventory_bound + out.invoice_lines_bound;
      toast.success(
        bound === 0
          ? `Nothing new matched. ${out.still_unmatched} still unmatched.`
          : `Matched ${out.inventory_bound} stock row${
              out.inventory_bound === 1 ? '' : 's'
            } and ${out.invoice_lines_bound} invoice line${
              out.invoice_lines_bound === 1 ? '' : 's'
            }, ${out.still_unmatched} still unmatched.`,
      );
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

// Forgetting a match has no mutation hook: both screens that offer it park
// `supplier_code_alias.forget` through `useDeferredRowAction` instead (D7), so the
// server applies it when the window lapses and the same three lists are refetched
// from the action's own invalidateKeys.
