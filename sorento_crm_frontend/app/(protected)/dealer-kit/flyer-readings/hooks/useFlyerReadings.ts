'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  getFlyerReading,
  listFlyerReadings,
  seedFromFlyerReading,
  uploadFlyerReading,
  type FlyerReading,
  type FlyerSeedInput,
  type FlyerSeedResult,
} from '../../services/flyerReadingService';

export const FLYER_READINGS_QUERY_KEY = 'dealer-kit-flyer-readings';

export function useFlyerReadingsQuery() {
  return useQuery({
    queryKey: [FLYER_READINGS_QUERY_KEY],
    queryFn: listFlyerReadings,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

/**
 * One reading and the report as it stands RIGHT NOW.
 *
 * `promotionId` is part of the key because the report is recomputed per
 * promotion: caching one answer under a promotion-blind key would show
 * "printed but not in this promotion" figures for a promotion nobody picked.
 *
 * `staleTime: 0` because the report is derived from the product master, which
 * moves. A reviewer who creates the missing product in another tab and comes
 * back must see the list shrink, not a cached copy telling them to do it again.
 */
export function useFlyerReadingQuery(readingId: string, promotionId: string | null) {
  return useQuery({
    queryKey: [FLYER_READINGS_QUERY_KEY, readingId, promotionId ?? ''],
    queryFn: () => getFlyerReading(readingId, promotionId),
    enabled: Boolean(readingId),
    // Changing the promotion is a new key and therefore a new query. Without
    // this the whole review - every section a reviewer was reading, and the
    // half-filled seed form under it - is replaced by a skeleton for the length
    // of a match run. The previous answer stays on screen and the header says
    // it is being recomputed.
    placeholderData: (previous) => previous,
    staleTime: 0,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

/**
 * Read a flyer. Synchronous on the server, so this resolves with the report.
 *
 * The detail cache is seeded from the response rather than invalidated: the
 * upload already paid for a match run, and a refetch on arrival would pay for a
 * second one and blank the screen it just filled.
 */
export function useUploadFlyerReading() {
  const queryClient = useQueryClient();

  return useMutation<FlyerReading, Error, { file: File; promotionId?: string | null }>({
    mutationFn: ({ file, promotionId }) => uploadFlyerReading(file, promotionId),
    onSuccess: (reading, { promotionId }) => {
      queryClient.setQueryData(
        [FLYER_READINGS_QUERY_KEY, reading.id, promotionId ?? ''],
        reading,
      );
      queryClient.invalidateQueries({ queryKey: [FLYER_READINGS_QUERY_KEY] });
      toast.success(`Read ${reading.pageCount} page${reading.pageCount === 1 ? '' : 's'}`);
    },
    onError: (error) => {
      // The backend says "not a PDF" and "larger than the 50 MB limit" in
      // words, so the message is passed through rather than replaced.
      toast.error(error.message || 'Could not read that flyer');
    },
  });
}

/**
 * Build the draft brochure.
 *
 * The pages list is invalidated because a new brochure has just appeared in it.
 * The READING is not: nothing about it changed, and refetching would throw away
 * the report the reviewer is still reading the skipped codes against.
 */
export function useSeedFromFlyerReading(readingId: string) {
  const queryClient = useQueryClient();

  return useMutation<FlyerSeedResult, Error, FlyerSeedInput>({
    mutationFn: (input) => seedFromFlyerReading(readingId, input),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['dealer-kit', 'pages'] });
      toast.success(`Draft v${result.version} created`);
    },
    onError: (error) => {
      toast.error(error.message || 'Could not create the draft brochure');
    },
  });
}
