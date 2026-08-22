'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  getPoWorklist,
  setKeyedStatus,
  type PoWorklistQuery,
} from '../services/poWorklistService';
import {
  KEYED_STATUS_LABELS,
  type KeyedStatusInput,
} from '../types/poWorklist.types';

/** Query key for one week's worklist. Exported so a keyed-status write can bust it. */
export function poWorklistKey(q: PoWorklistQuery = {}) {
  return ['scm', 'reorder', 'po-worklist', q.run_id ?? null] as const;
}

/**
 * The PO creation worklist (AC-E2.1).
 *
 * The decisions are frozen, but the keyed status is not: somebody else may be keying
 * the same run, so this refetches on focus rather than caching for a sitting the way
 * the report does. That is the difference between reading a frozen position and
 * working a shared queue.
 */
export function usePoWorklist(q: PoWorklistQuery = {}, enabled = true) {
  return useQuery({
    queryKey: poWorklistKey(q),
    queryFn: () => getPoWorklist(q),
    enabled,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
    retry: 1,
  });
}

/**
 * Set the keyed-into-AutoCount status (AC-E2.2).
 *
 * The toast names the row and the new state, because the status column is the point
 * of the screen and a silent success on a shared queue leaves two people guessing
 * whether the click landed.
 */
export function useSetKeyedStatus(q: PoWorklistQuery = {}) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      productCode,
      input,
    }: {
      productCode: string;
      input: KeyedStatusInput;
    }) => setKeyedStatus(productCode, input),
    onSuccess: (result) => {
      void qc.invalidateQueries({ queryKey: poWorklistKey(q) });
      const where = result.warehouse_code ? ` @ ${result.warehouse_code}` : '';
      toast.success(
        `${result.product_code}${where} - ${KEYED_STATUS_LABELS[result.keyed_status]}`,
      );
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
