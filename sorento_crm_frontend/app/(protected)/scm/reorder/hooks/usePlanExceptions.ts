'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  decidePlanException,
  getPlanExceptions,
  type PlanExceptionQuery,
} from '../services/planExceptionService';
import {
  EXCEPTION_STATUS_LABELS,
  type PlanExceptionDecisionInput,
} from '../types/planException.types';

/** Query key for one run's batch. Exported so a decision can bust it. */
export function planExceptionsKey(q: PlanExceptionQuery = {}) {
  return ['scm', 'reorder', 'plan-exceptions', q.run_id ?? null, q.status ?? null] as const;
}

/**
 * The exception batch for one run (AC-D2).
 *
 * Frozen at the moment the upload was confirmed, so it does not go stale on its own -
 * but the STATUSES do, because more than one person works the queue. Refetches on focus
 * for the same reason the PO worklist does: coming back to the tab to find a row you
 * already approved still sitting open is how two people decide it twice.
 */
export function usePlanExceptions(q: PlanExceptionQuery = {}, enabled = true) {
  return useQuery({
    queryKey: planExceptionsKey(q),
    queryFn: () => getPlanExceptions(q),
    enabled,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
    retry: 1,
  });
}

/**
 * Approve or reject one exception (AC-D6).
 *
 * The toast names the product and the outcome. A decision that amends a supplier's
 * placed order is not a thing to confirm silently.
 */
export function useDecidePlanException(q: PlanExceptionQuery = {}) {
  const qc = useQueryClient();
  return useMutation({
    // `productCode` rides alongside rather than inside the payload: the server keys the
    // decision by `exception_id` and has no use for it, but the toast must name the row
    // a person was looking at, not an opaque id.
    mutationFn: ({ input }: { productCode: string; input: PlanExceptionDecisionInput }) =>
      decidePlanException(input),
    onSuccess: (result, { productCode }) => {
      void qc.invalidateQueries({ queryKey: planExceptionsKey(q) });
      toast.success(`${productCode} - ${EXCEPTION_STATUS_LABELS[result.status]}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
