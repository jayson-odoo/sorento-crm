'use client';

/**
 * Reading planning changes (`PLAN-so-book-diff-replanning.md`, part 3 of
 * `PLAN-scm-cs-planning-uat.md`).
 *
 * TWO READS AND NO WRITE. The batch page is retired: a planning change is a change to a
 * PLAN, and the plan has one screen, so the decision and the Confirm both belong to the
 * fulfilment board (`POST .../sales-orders/{pso_id}/confirm` carrying `batch_id`). The
 * mutation hook that used to sit here wrote decisions and pressed Apply for that page and
 * had no consumer left once it went.
 */
import { useQuery } from '@tanstack/react-query';
import {
  getPlanningChangeBatch,
  listPlanningChangeBatches,
} from '../services/planningChangeService';
import type { PlanningChangeListParams } from '../types/planningChange.types';

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
