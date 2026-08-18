'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  applyPlanningChanges,
  getPlanningChangeBatch,
  listPlanningChangeBatches,
  updatePlanningChangeRow,
} from '../services/planningChangeService';
import type {
  PlanningChangeDecision,
  PlanningChangeListParams,
} from '../types/planningChange.types';

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
    mutationFn: ({ rowId, decision }: { rowId: string; decision: PlanningChangeDecision }) =>
      updatePlanningChangeRow(batchId, rowId, { decision }),
    onSuccess: () => invalidate(),
    onError: (error: Error) => toast.error(error.message),
  });

  const apply = useMutation({
    mutationFn: () => applyPlanningChanges(batchId),
    onSuccess: (result) => {
      invalidate();
      if (result.already_applied) {
        toast.success('This batch was already applied.');
        return;
      }
      if (result.failed_orders.length > 0) {
        toast.warning(
          `Applied, but ${result.failed_orders.length} order${
            result.failed_orders.length === 1 ? '' : 's'
          } could not be written.`,
        );
        return;
      }
      toast.success(`Applied ${result.applied_orders.length} order${
        result.applied_orders.length === 1 ? '' : 's'
      }.`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { updateDecision, apply };
}
