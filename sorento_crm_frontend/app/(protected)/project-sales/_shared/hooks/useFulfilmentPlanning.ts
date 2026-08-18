'use client';

import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  getReconciliation,
  listFulfilmentPlanning,
  rerunReconciliation,
} from '../services/fulfilmentPlanningService';
import type { FulfilmentPlanningListParams } from '../types/fulfilmentPlanning.types';
import { SALES_ORDERS_KEY, SALES_ORDER_KEY } from './useProjectSalesOrders';

export const FULFILMENT_PLANNING_KEY = 'project-fulfilment-planning';
export const RECONCILIATION_KEY = 'project-so-reconciliation';

export const fulfilmentPlanningKey = (params: FulfilmentPlanningListParams) => [
  FULFILMENT_PLANNING_KEY,
  params,
];

export function useFulfilmentPlanning(params: FulfilmentPlanningListParams = {}) {
  return useQuery({
    queryKey: fulfilmentPlanningKey(params),
    queryFn: () => listFulfilmentPlanning(params),
    // The page and the search both change the key, so without this the grid empties to a
    // skeleton on every keystroke and every page turn. The previous page stays on screen
    // until the next one answers.
    placeholderData: keepPreviousData,
  });
}

/**
 * The reconciliation for one order, fetched when its sheet is open.
 *
 * `enabled` rather than an always-on query: the list carries five columns of the same
 * answer already, and pre-fetching a summary per row would run the mapping for orders
 * nobody opened.
 */
export function useReconciliation(psoId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: [RECONCILIATION_KEY, psoId ?? ''],
    queryFn: () => getReconciliation(psoId as string),
    enabled: Boolean(psoId) && enabled,
    // One retry, not the default three: the sheet is open in front of somebody, and three
    // backed-off attempts leave them looking at a skeleton for ten seconds before the
    // failure is admitted.
    retry: 1,
  });
}

/**
 * Re-running writes the links it can prove, so it invalidates the sales-order queries too:
 * the review state is shown on the project's SO list and on the SO detail header, and a
 * stale one there says an order still needs reconciling after it has been cleared.
 */
export function useReconciliationMutations() {
  const queryClient = useQueryClient();

  const rerun = useMutation({
    mutationFn: (psoId: string) => rerunReconciliation(psoId),
    onSuccess: (summary) => {
      queryClient.invalidateQueries({ queryKey: [FULFILMENT_PLANNING_KEY] });
      queryClient.invalidateQueries({ queryKey: [RECONCILIATION_KEY] });
      queryClient.invalidateQueries({ queryKey: [SALES_ORDERS_KEY] });
      queryClient.invalidateQueries({ queryKey: [SALES_ORDER_KEY] });
      const open = summary.exceptions.length;
      if (open === 0) {
        toast.success('Reconciled. This sales order is ready for CS review.');
      } else {
        toast.warning(
          `${open} exception${open === 1 ? '' : 's'} still to clear on this sales order.`,
        );
      }
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { rerun };
}
