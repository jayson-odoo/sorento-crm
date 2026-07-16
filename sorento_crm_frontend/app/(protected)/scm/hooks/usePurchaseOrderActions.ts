'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  bulkConfirmPurchaseOrders,
  createGrFromPurchaseOrder,
} from '../services/purchaseOrderService';

// Confirm (draft→active) and create-GR change what counts as ON-ORDER (M4-D5/D6),
// so besides the PO list we must invalidate every dashboard read that surfaces
// on_order / net position — else a user who viewed the dashboard sees stale
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
 * Bulk-confirm draft POs (draft_recommendation → active) and create-GR-from-PO
 * (M4-D6). Both invalidate the PO list AND the on-order-bearing dashboard reads
 * so status chips + net-position/on-order figures refresh. The caller owns the
 * success toast (GR ref / confirmed count).
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

  return { confirm, createGr };
}
