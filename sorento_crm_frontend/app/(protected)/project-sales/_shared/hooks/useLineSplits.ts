'use client';

import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { getLineSplits, saveLineSplits } from '../services/lineSplitService';
import type { LineSplitsSaveBody } from '../types/lineSplit.types';
import {
  FULFILMENT_PLANNING_KEY,
  PLANNING_BOARD_KEY,
} from './useFulfilmentPlanning';
import {
  ORDER_INQUIRY_HEADER_LINES_KEY,
  ORDER_INQUIRY_WORKLIST_KEY,
} from './useOrderInquiry';

export const LINE_SPLITS_KEY = 'project-so-line-splits';

/** One order's split read, the same key and read for every caller. */
function lineSplitsQuery(psoId: string | null | undefined, enabled: boolean) {
  return {
    queryKey: [LINE_SPLITS_KEY, psoId ?? ''],
    // A read that answers no body is "no split lines" (`null`, the popups' empty state), not
    // a failed read: React Query refuses `undefined` as data.
    queryFn: async () => (await getLineSplits(psoId as string)) ?? null,
    enabled: Boolean(psoId) && enabled,
  };
}

/** OI-LINE-SPLIT: the whole-SO split view's data and its one Save. */
export function useLineSplits(
  psoId: string | null | undefined,
  enabled = true,
) {
  const queryClient = useQueryClient();
  const query = useQuery(lineSplitsQuery(psoId, enabled));
  const save = useMutation({
    mutationFn: (body: LineSplitsSaveBody) =>
      saveLineSplits(psoId as string, body),
    onSuccess: (data) => {
      queryClient.setQueryData([LINE_SPLITS_KEY, psoId ?? ''], data);
      void queryClient.invalidateQueries({ queryKey: [PLANNING_BOARD_KEY] });
      void queryClient.invalidateQueries({
        queryKey: [FULFILMENT_PLANNING_KEY],
      });
      void queryClient.invalidateQueries({
        queryKey: [ORDER_INQUIRY_WORKLIST_KEY],
      });
      void queryClient.invalidateQueries({
        queryKey: [ORDER_INQUIRY_HEADER_LINES_KEY],
      });
      toast.success('Splits saved');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to save the splits');
    },
  });
  return { query, save };
}

/**
 * OI-SPLIT-GUIDE (UAC F14): several orders' split reads at once, in order. The guided Confirm
 * reads every page while it is open, so a page is ready by the time it is reached (and its
 * Next stays off only while its own read is still out). A null id reads nothing.
 */
export function useLineSplitsReads(psoIds: readonly (string | null)[]) {
  return useQueries({ queries: psoIds.map((psoId) => lineSplitsQuery(psoId, true)) });
}
