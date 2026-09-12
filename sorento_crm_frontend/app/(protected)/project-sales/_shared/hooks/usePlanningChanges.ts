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
import { useQueries, useQuery } from '@tanstack/react-query';
import {
  getPlanningChangeBatch,
  listPlanningChangeBatches,
} from '../services/planningChangeService';
import type {
  PlanningChangeBatch,
  PlanningChangeListParams,
} from '../types/planningChange.types';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export const PLANNING_CHANGE_BATCHES_KEY = 'planning-change-batches';
export const PLANNING_CHANGE_BATCH_KEY = 'planning-change-batch';

export function usePlanningChangeBatches(params: PlanningChangeListParams = {}) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [PLANNING_CHANGE_BATCHES_KEY, params],
    queryFn: () => listPlanningChangeBatches(params),
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
 * Several batches by id, one query each, same key family as `usePlanningChangeBatch`
 * (`PLAN-scm-board-picks-up-pending-change.md`, change 5): the fulfilment board now names
 * a batch PER ORDER (`BoardOrderStanding.pending_change_batch_id`) rather than reading one
 * off the URL alone, so two orders on two different pending changes both need their batch
 * fetched - and a batch already cached under `usePlanningChangeBatch`'s key (the `?batch=`
 * deep-link case) is not fetched twice.
 *
 * Named `...ByIds`, not `usePlanningChangeBatches` - that name is already the LIST hook
 * above (`listPlanningChangeBatches`, filtered by params), a different read entirely.
 */
export function usePlanningChangeBatchesByIds(batchIds: string[]) {
  return useQueries({
    queries: batchIds.map((batchId) => ({
      queryKey: [PLANNING_CHANGE_BATCH_KEY, batchId],
      queryFn: (): Promise<PlanningChangeBatch> => getPlanningChangeBatch(batchId),
    })),
  });
}
