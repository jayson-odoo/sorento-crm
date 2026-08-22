'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  bulkConfirmPurchaseOrders,
  bulkDeletePurchaseOrders,
  createGrFromPurchaseOrder,
} from '../services/purchaseOrderService';
// Deleting a PO can UNPLACE order-inquiry rows that were tagged to one of its lines
// (see `bulkDeletePurchaseOrders`'s docstring) - read-only import of the project-sales
// screen's own query-key constants, so its worklist / row grid refetch the instant a
// row comes back onto the board instead of the buyer finding out on next reload.
import {
  ORDER_INQUIRY_KEY,
  ORDER_INQUIRY_ROWS_KEY,
  ORDER_INQUIRY_SUMMARY_KEY,
  ORDER_INQUIRY_WORKLIST_KEY,
  ORDER_INQUIRY_WORKLIST_SUMMARY_KEY,
} from '@/app/(protected)/project-sales/_shared/hooks/useOrderInquiry';

// Confirm (draft→active) and create-GR change what counts as ON-ORDER (M4-D5/D6),
// so besides the PO list we must invalidate every dashboard read that surfaces
// on_order / net position - else a user who viewed the dashboard sees stale
// incoming-supply numbers until staleTime/refocus.
const AFFECTED_KEYS = [
  ['scm', 'purchase-orders'],
  ['scm', 'net-position'],
  ['scm', 'rollups'],
  ['scm', 'products'],
  ['scm', 'warehouses'],
  ['scm', 'suppliers'],
];

/**
 * Bulk-confirm draft POs (draft_recommendation → active), create-GR-from-PO
 * (M4-D6), and bulk-delete. All three invalidate the PO list AND the
 * on-order-bearing dashboard reads so status chips + net-position/on-order
 * figures refresh; bulk-delete ALSO invalidates the project-sales order-inquiry
 * reads, since deleting a PO can unplace a row tagged to one of its lines. The
 * caller owns the success toast (GR ref / confirmed count / deleted + unplaced
 * counts).
 */
export function usePurchaseOrderActions() {
  const queryClient = useQueryClient();
  const invalidate = () =>
    AFFECTED_KEYS.forEach((queryKey) => queryClient.invalidateQueries({ queryKey }));

  const confirm = useMutation({
    mutationFn: (ids: string[]) => bulkConfirmPurchaseOrders(ids),
    onSuccess: () => void invalidate(),
  });

  const createGr = useMutation({
    mutationFn: (id: string) => createGrFromPurchaseOrder(id),
    onSuccess: () => void invalidate(),
  });

  const bulkDelete = useMutation({
    mutationFn: (ids: string[]) => bulkDeletePurchaseOrders(ids),
    onSuccess: () => {
      invalidate();
      [
        ORDER_INQUIRY_ROWS_KEY,
        ORDER_INQUIRY_SUMMARY_KEY,
        ORDER_INQUIRY_KEY,
        ORDER_INQUIRY_WORKLIST_KEY,
        ORDER_INQUIRY_WORKLIST_SUMMARY_KEY,
      ].forEach((queryKey) => queryClient.invalidateQueries({ queryKey: [queryKey] }));
    },
  });

  return { confirm, createGr, bulkDelete };
}
