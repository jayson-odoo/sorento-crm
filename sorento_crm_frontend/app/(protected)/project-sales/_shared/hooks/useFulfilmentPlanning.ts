'use client';

import { useEffect } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  adoptSalesOrder,
  confirmSupply,
  getReconciliation,
  getSupply,
  listFulfilmentPlanning,
  rerunReconciliation,
} from '../services/fulfilmentPlanningService';
import type {
  AdoptSalesOrderResult,
  ConfirmSupplyBody,
  FulfilmentPlanningListParams,
} from '../types/fulfilmentPlanning.types';
import { ORDER_INQUIRY_ROWS_KEY, ORDER_INQUIRY_SUMMARY_KEY } from './useOrderInquiry';
import { SALES_ORDERS_KEY, SALES_ORDER_KEY } from './useProjectSalesOrders';

export const FULFILMENT_PLANNING_KEY = 'project-fulfilment-planning';
export const RECONCILIATION_KEY = 'project-so-reconciliation';
export const SUPPLY_KEY = 'project-so-supply';

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
 * Start planning an outstanding core sales order.
 *
 * Separate from `useReconciliationMutations` because it is the only mutation on this screen
 * that a row can carry before any planning record exists, and it is the only one whose
 * success has to hand the caller an id it did not have (the sheet opens on the record that
 * was just created).
 *
 * No toast on the idempotent path beyond the truth: pressing Start planning on an order
 * somebody else already started is not an error and must not read like one.
 */
export function useFulfilmentPlanningMutations() {
  const queryClient = useQueryClient();

  const adopt = useMutation({
    mutationFn: (salesOrderId: string) => adoptSalesOrder(salesOrderId),
    onSuccess: (result: AdoptSalesOrderResult) => {
      queryClient.invalidateQueries({ queryKey: [FULFILMENT_PLANNING_KEY] });
      queryClient.invalidateQueries({ queryKey: [SALES_ORDERS_KEY] });
      toast.success(
        result.already_adopted
          ? `${result.so_number} is already being planned.`
          : `${result.so_number} is ready to plan.`,
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { adopt };
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
 * The composition for one order, fetched with the sheet for the same reason the
 * reconciliation is: it reads live stock, claims and incoming per line, and running that
 * for every row of the worklist would price the whole list on nobody's behalf.
 */
export function useSupply(psoId: string | undefined, enabled = true) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: [SUPPLY_KEY, psoId ?? ''],
    queryFn: () => getSupply(psoId as string),
    enabled: Boolean(psoId) && enabled,
    retry: 1,
    // A focus refetch mid-composition churns the proposal under CS for no decision
    // change; the confirm rechecks live facts anyway, so the sheet does not need to.
    refetchOnWindowFocus: false,
    staleTime: 15_000,
  });

  // The supply read is the one that notices an out-of-band change (it rechecks live
  // facts and may flip the decision to challenged), so when its review_state disagrees
  // with the cached reconciliation the pill sources are stale, not the sheet: refetch
  // them rather than letting "Confirmed" sit over a composition that says otherwise.
  const freshState = query.data?.review_state;
  useEffect(() => {
    if (!psoId || freshState === undefined) return;
    const summary = queryClient.getQueryData<{ review_state?: string | null }>([
      RECONCILIATION_KEY,
      psoId,
    ]);
    if (summary && (summary.review_state ?? null) !== (freshState ?? null)) {
      void queryClient.invalidateQueries({ queryKey: [RECONCILIATION_KEY, psoId] });
      void queryClient.invalidateQueries({ queryKey: [FULFILMENT_PLANNING_KEY] });
    }
  }, [psoId, freshState, queryClient]);

  return query;
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

  /**
   * One press confirms every line (AC-C01). It invalidates the same four key families the
   * re-run does, plus the order inquiry: the confirmed Buy residual is what purchasing is
   * handed, so a stale inquiry list is the one place the decision would look like it had
   * not happened.
   *
   * The error toast is deliberately short. A refusal names each failing line, and that
   * list belongs on the sheet beside the lines, not in a toast that scrolls away.
   */
  const confirm = useMutation({
    mutationFn: ({ psoId, body }: { psoId: string; body: ConfirmSupplyBody }) =>
      confirmSupply(psoId, body),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: [FULFILMENT_PLANNING_KEY] });
      queryClient.invalidateQueries({ queryKey: [RECONCILIATION_KEY] });
      queryClient.invalidateQueries({ queryKey: [SUPPLY_KEY] });
      queryClient.invalidateQueries({ queryKey: [SALES_ORDERS_KEY] });
      queryClient.invalidateQueries({ queryKey: [SALES_ORDER_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_ROWS_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_SUMMARY_KEY] });
      const rows = result.inquiry_rows_created;
      toast.success(
        `Confirmed as revision ${result.revision_no}. ${rows} purchase row${
          rows === 1 ? '' : 's'
        } handed over.`,
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { rerun, confirm };
}
