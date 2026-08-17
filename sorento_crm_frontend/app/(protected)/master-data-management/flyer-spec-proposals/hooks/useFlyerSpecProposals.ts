'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  applyFlyerSpecProposals,
  getFlyerSpecProposals,
  listFlyerSpecBatches,
  proposeFlyerSpecs,
  type FlyerSpecApplyResult,
  type FlyerSpecBatch,
  type FlyerSpecProposals,
} from '../services/flyerSpecProposalService';

export const FLYER_SPEC_BATCHES_QUERY_KEY = 'flyer-spec-proposal-batches';
export const FLYER_SPEC_PROPOSALS_QUERY_KEY = 'flyer-spec-proposals';

/** How often a pass that is still running is asked about again. Same as the read. */
const PROPOSING_POLL_MS = 3000;

/**
 * Every proposal pass, for the Master Data list.
 *
 * Polls only while something is `proposing` and stops the moment nothing is, so
 * a merchandiser watching a pass they just started sees it flip without touching
 * anything, and a merchandiser reading the list costs the server nothing.
 */
export function useFlyerSpecBatchesQuery() {
  return useQuery({
    queryKey: [FLYER_SPEC_BATCHES_QUERY_KEY],
    queryFn: listFlyerSpecBatches,
    refetchInterval: (query) =>
      (query.state.data ?? []).some((row) => row.status === 'proposing')
        ? PROPOSING_POLL_MS
        : false,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

/**
 * The batch for one reading, and its rows.
 *
 * `staleTime: 0` because a proposal is a claim about the product master, which
 * moves: somebody who fixed a spec in another tab must come back to a row that
 * has stopped asking to be fixed, not to a cached copy telling them to do it
 * again. The apply re-checks it server-side either way (AC-C.2), so a stale
 * screen is a wasted click rather than a wrong write - but a wasted click on a
 * hundred-row batch is what makes the screen feel untrustworthy.
 *
 * `enabled` is a caller's to withhold: the route needs `master_data.products.edit`
 * as well as the dealer-kit slug, so a surface that renders for somebody without it
 * (the reading page's section, which still says what it is) passes `false` rather
 * than firing a request that can only come back 403.
 */
export function useFlyerSpecProposalsQuery(
  readingId: string,
  options: { enabled?: boolean } = {},
) {
  const { enabled = true } = options;

  return useQuery<FlyerSpecProposals>({
    queryKey: [FLYER_SPEC_PROPOSALS_QUERY_KEY, readingId],
    queryFn: () => getFlyerSpecProposals(readingId),
    enabled: enabled && Boolean(readingId),
    refetchInterval: (query) =>
      query.state.data?.status === 'proposing' ? PROPOSING_POLL_MS : false,
    staleTime: 0,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

/**
 * Read this flyer onto the products it names.
 *
 * Both keys are invalidated: the section the button sits in reads the first, and
 * the Master Data list reads the second, and a merchandiser who proposes from
 * the dealer kit and then opens the list must not find it missing.
 *
 * A 202 does not mean the pass is on its way. The route answers 202 with the row
 * already `failed` when it could not queue the job at all, and telling somebody
 * their flyer is being read in the background when nothing was queued is telling
 * them something that will never happen - so the row decides the toast.
 */
export function useProposeFlyerSpecs(readingId: string) {
  const queryClient = useQueryClient();

  return useMutation<FlyerSpecBatch, Error, void>({
    mutationFn: () => proposeFlyerSpecs(readingId),
    onSuccess: (batch) => {
      queryClient.invalidateQueries({
        queryKey: [FLYER_SPEC_PROPOSALS_QUERY_KEY, readingId],
      });
      queryClient.invalidateQueries({
        queryKey: [FLYER_SPEC_BATCHES_QUERY_KEY],
      });
      if (batch.status === 'failed') {
        toast.error(
          batch.error_message ||
            'Could not read specifications from this flyer',
        );
        return;
      }
      toast.success(
        'Reading specifications from this flyer - the counts appear here',
      );
    },
    onError: (error) => {
      toast.error(
        error.message || 'Could not read specifications from this flyer',
      );
    },
  });
}

/**
 * Write the ticked rows to the product master.
 *
 * The batch is invalidated afterwards and that is the point: an applied row must
 * come back as something the master already holds, rather than sitting there as
 * a proposal somebody applies again on their next visit.
 *
 * The success toast counts only what was WRITTEN. A green line over three silent
 * refusals is the failure this endpoint is shaped to prevent, so the refusals
 * are the caller's result table to render and nothing here summarises them away.
 */
export function useApplyFlyerSpecProposals(readingId: string) {
  const queryClient = useQueryClient();

  return useMutation<FlyerSpecApplyResult, Error, string[]>({
    mutationFn: (proposalIds) =>
      applyFlyerSpecProposals(readingId, proposalIds),
    onSuccess: (result) => {
      queryClient.invalidateQueries({
        queryKey: [FLYER_SPEC_PROPOSALS_QUERY_KEY, readingId],
      });
      queryClient.invalidateQueries({
        queryKey: [FLYER_SPEC_BATCHES_QUERY_KEY],
      });
      if (result.applied.length > 0) {
        toast.success(
          `${result.applied.length} specification value${result.applied.length === 1 ? '' : 's'} written`,
        );
      }
    },
    onError: (error) => {
      toast.error(error.message || 'Could not apply these specifications');
    },
  });
}
