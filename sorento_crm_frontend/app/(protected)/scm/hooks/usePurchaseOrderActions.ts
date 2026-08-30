'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  bulkConfirmPurchaseOrders,
  bulkDeletePurchaseOrders,
  createGrFromPurchaseOrder,
} from '../services/purchaseOrderService';
// Confirming a PO LINKS raised order-inquiry rows (the cascade runs on confirm,
// `PurchaseOrderService.bulk_confirm`) and deleting one UNPLACES the rows tagged to its
// lines - read-only import of the project-sales screen's own query-key constants, so its
// worklist, its cards and its schedule cells refetch the instant a row changes hands
// instead of the buyer finding out on the next reload (AC-I13).
import {
  ORDER_INQUIRY_KEY,
  ORDER_INQUIRY_PO_CANDIDATES_KEY,
  ORDER_INQUIRY_PO_DETAIL_KEY,
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
 * figures refresh; confirm and bulk-delete ALSO invalidate the project-sales
 * order-inquiry reads, since confirming a PO links raised rows to its lines and
 * deleting one unplaces them again. The caller owns the success toast (GR ref /
 * confirmed count / deleted + unplaced counts).
 */
export function usePurchaseOrderActions() {
  const queryClient = useQueryClient();
  const invalidate = () =>
    AFFECTED_KEYS.forEach((queryKey) => queryClient.invalidateQueries({ queryKey }));
  // Every order-inquiry read a link can move: the per-project rows and summary, the
  // inquiry itself, and purchasing's cross-project worklist WITH its summary - the
  // summary is where the three cards' `kinds` facet lives, so leaving it out would flip
  // a cell to Use PO under cards that still counted it as a Buy. The last two are the
  // "Place on PO" dialog's own reads, invalidated for the same reason the order-inquiry
  // screen's own placement hook invalidates them: a purchase order this pass confirmed
  // or deleted is a candidate whose remaining quantity has changed, or a header and set
  // of lines that no longer exist at all.
  const invalidateOrderInquiries = () =>
    [
      ORDER_INQUIRY_ROWS_KEY,
      ORDER_INQUIRY_SUMMARY_KEY,
      ORDER_INQUIRY_KEY,
      ORDER_INQUIRY_WORKLIST_KEY,
      ORDER_INQUIRY_WORKLIST_SUMMARY_KEY,
      ORDER_INQUIRY_PO_CANDIDATES_KEY,
      ORDER_INQUIRY_PO_DETAIL_KEY,
    ].forEach((queryKey) => queryClient.invalidateQueries({ queryKey: [queryKey] }));

  const confirm = useMutation({
    mutationFn: (ids: string[]) => bulkConfirmPurchaseOrders(ids),
    onSuccess: () => {
      invalidate();
      // AC-I13: the confirm's own auto-place pass has just linked whatever raised rows
      // this purchase order was raised for, so the cell those rows sit in must flip from
      // Buy to Use PO here rather than on a reload.
      invalidateOrderInquiries();
    },
  });

  const createGr = useMutation({
    mutationFn: (id: string) => createGrFromPurchaseOrder(id),
    onSuccess: () => void invalidate(),
  });

  const bulkDelete = useMutation({
    mutationFn: (ids: string[]) => bulkDeletePurchaseOrders(ids),
    onSuccess: () => {
      invalidate();
      invalidateOrderInquiries();
    },
  });

  return { confirm, createGr, bulkDelete };
}
