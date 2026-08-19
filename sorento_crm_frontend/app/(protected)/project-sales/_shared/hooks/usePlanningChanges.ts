'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  applyPlanningChanges,
  getPlanningChangeBatch,
  listPlanningChangeBatches,
  updatePlanningChangeRow,
} from '../services/planningChangeService';
import type { ConfirmLine } from '../types/fulfilmentPlanning.types';
import type {
  PlanningChangeDecision,
  PlanningChangeListParams,
} from '../types/planningChange.types';
import { FULFILMENT_PLANNING_KEY, PLANNING_BOARD_KEY } from './useFulfilmentPlanning';
import {
  ORDER_INQUIRY_ROWS_KEY,
  ORDER_INQUIRY_SUMMARY_KEY,
  ORDER_INQUIRY_WORKLIST_KEY,
  ORDER_INQUIRY_WORKLIST_SUMMARY_KEY,
} from './useOrderInquiry';

export const PLANNING_CHANGE_BATCHES_KEY = 'planning-change-batches';
export const PLANNING_CHANGE_BATCH_KEY = 'planning-change-batch';

export function usePlanningChangeBatches(params: PlanningChangeListParams = {}) {
  return useQuery({
    queryKey: [PLANNING_CHANGE_BATCHES_KEY, params],
    queryFn: () => listPlanningChangeBatches(params),
    placeholderData: (previous) => previous,
  });
}

export function usePlanningChangeBatch(batchId: string | undefined) {
  return useQuery({
    queryKey: [PLANNING_CHANGE_BATCH_KEY, batchId],
    queryFn: () => getPlanningChangeBatch(batchId as string),
    enabled: Boolean(batchId),
  });
}

/**
 * Switching a row's decision and applying the batch (AC-R04, AC-R05).
 *
 * Both invalidate the batch AND the list: the batch page re-renders the row it just changed,
 * and the list's Pending/Applied counts must not lag the same change.
 */
export function usePlanningChangeMutations(batchId: string) {
  const queryClient = useQueryClient();

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: [PLANNING_CHANGE_BATCH_KEY, batchId] });
    queryClient.invalidateQueries({ queryKey: [PLANNING_CHANGE_BATCHES_KEY] });
  };

  const updateDecision = useMutation({
    mutationFn: ({
      rowId,
      decision,
      composition,
    }: {
      rowId: string;
      decision: PlanningChangeDecision;
      composition?: ConfirmLine;
    }) => updatePlanningChangeRow(batchId, rowId, { decision, composition }),
    onSuccess: () => {
      invalidate();
      // The write is otherwise invisible: the captain's own complaint was a decision that
      // recorded but did nothing at Apply. Every write says so, right away.
      toast.success('Saved - applied when you press Apply');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const apply = useMutation({
    mutationFn: () => applyPlanningChanges(batchId),
    onSuccess: (result) => {
      invalidate();
      // Apply writes through the same supply-confirmation path Fulfilment Planning uses
      // (module docstring): the board reads live holds, and purchasing's Order Inquiry list
      // is exactly what a released/replanned/reduced line hands over. Leaving either stale
      // would show a planner a Reserve their own Apply had just released, or hide the rows
      // purchasing was just told about.
      queryClient.invalidateQueries({ queryKey: [FULFILMENT_PLANNING_KEY] });
      queryClient.invalidateQueries({ queryKey: [PLANNING_BOARD_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_ROWS_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_SUMMARY_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_WORKLIST_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_WORKLIST_SUMMARY_KEY] });
      if (result.already_applied) {
        toast.success('This batch was already applied.');
        return;
      }
      if (result.failed_orders.length > 0 && result.applied_orders.length === 0) {
        toast.warning(
          `Applied, but ${result.failed_orders.length} order${
            result.failed_orders.length === 1 ? '' : 's'
          } could not be written.`,
        );
      }
      // The successful case's own toast + scroll-to-highlight is `PlanningChangeBatchClient`'s
      // job, once the refetch this `invalidate()` triggers lands with the real per-order
      // revision numbers (`SO346436 revised to rev 1 · 1 line back on the board`) - this
      // mutation only knows `applied_orders`/`failed_orders`, not what actually got written.
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { updateDecision, apply };
}
