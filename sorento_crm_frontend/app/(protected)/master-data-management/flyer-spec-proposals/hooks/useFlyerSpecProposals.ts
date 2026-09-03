'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';

import {
  addFlyerSpecProposalRow,
  applyFlyerSpecProposals,
  dismissFlyerSpecProposal,
  editFlyerSpecProposal,
  getFlyerSpecProposals,
  listFlyerSpecBatches,
  proposeFlyerSpecs,
  type FlyerSpecApplyResult,
  type FlyerSpecBatch,
  type FlyerSpecProposal,
  type FlyerSpecProposals,
} from '../services/flyerSpecProposalService';
import type { SpecProposal } from '@/components/spec-proposals';
import { getApplicableSpecKeys } from '../../product-specifications/services/productSpecService';
import { APPLICABLE_KEY } from '../../products/hooks/useProductSpecTable';

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

/**
 * Every act that changes ONE row of the batch invalidates the same two keys.
 *
 * The row's `kind` and the batch's counts are both server-computed, and both
 * appear on this screen: an edit that flipped a row to `unchanged` while the
 * header still said "3 change" would be the screen disagreeing with itself.
 */
function useRowMutationInvalidation(readingId: string) {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({
      queryKey: [FLYER_SPEC_PROPOSALS_QUERY_KEY, readingId],
    });
    queryClient.invalidateQueries({
      queryKey: [FLYER_SPEC_BATCHES_QUERY_KEY],
    });
  };
}

/**
 * Correct one proposal's value in place (AC-F.2).
 *
 * No success toast. The corrected value, its new pill and its "edited" mark are
 * the answer, and they are already on screen - a toast over a cell somebody is
 * looking at is noise on a screen where a reviewer may correct twenty rows.
 */
export function useEditFlyerSpecProposal(readingId: string) {
  const invalidate = useRowMutationInvalidation(readingId);

  return useMutation<
    FlyerSpecProposal,
    Error,
    { proposalId: string; value: SpecProposal['value'] }
  >({
    mutationFn: ({ proposalId, value }) =>
      editFlyerSpecProposal(readingId, proposalId, value),
    onSuccess: invalidate,
    onError: (error) => {
      toast.error(error.message || 'Could not save that value');
    },
  });
}

/**
 * Add a specification the flyer stated in a way no rule caught (AC-G.1).
 *
 * The returned row is written into the cached batch BEFORE the refetch is asked
 * for. The screen ticks the new row the moment the call answers and counts its
 * replacements off the cached batch, so a row that only reached the cache a
 * round trip later would be a ticked `conflict` the confirm dialog did not
 * know about, and Apply would overwrite a value a person set without naming it.
 */
export function useAddFlyerSpecProposalRow(readingId: string) {
  const queryClient = useQueryClient();
  const invalidate = useRowMutationInvalidation(readingId);

  return useMutation<
    FlyerSpecProposal,
    Error,
    { product_id: string; spec_key: string; value: SpecProposal['value'] }
  >({
    mutationFn: (input) => addFlyerSpecProposalRow(readingId, input),
    onSuccess: (row, input) => {
      queryClient.setQueryData<FlyerSpecProposals>(
        [FLYER_SPEC_PROPOSALS_QUERY_KEY, readingId],
        (current) =>
          current ? seedProposalRow(current, input.product_id, row) : current,
      );
      invalidate();
      toast.success(`${row.label} added to this flyer's proposals`);
    },
    onError: (error) => {
      toast.error(error.message || 'Could not add that specification');
    },
  });
}

/** The cached batch with `row` placed in `productId`'s group, replacing any row of the same id. */
export function seedProposalRow(
  batch: FlyerSpecProposals,
  productId: string,
  row: FlyerSpecProposal,
): FlyerSpecProposals {
  return {
    ...batch,
    groups: batch.groups.map((group) => {
      if (group.product_id !== productId) return group;
      const others = group.proposals.filter(
        (existing) => existing.id !== row.id,
      );
      return { ...group, proposals: [...others, row] };
    }),
  };
}

/** Take a proposal off the batch for good (AC-G.3). */
export function useDismissFlyerSpecProposal(readingId: string) {
  const invalidate = useRowMutationInvalidation(readingId);

  return useMutation<FlyerSpecBatch, Error, string>({
    mutationFn: (proposalId) => dismissFlyerSpecProposal(readingId, proposalId),
    onSuccess: () => {
      invalidate();
      toast.success('Proposal dismissed');
    },
    onError: (error) => {
      toast.error(error.message || 'Could not dismiss that proposal');
    },
  });
}

/**
 * Which keys this product may carry, for the add-a-specification picker.
 *
 * The SAME call and the SAME query key the product's Specifications tab uses, so
 * a merchandiser who opens the picker here and then on the product is offered one
 * answer rather than two, and the cache is shared. Applicability is decided
 * server-side by derivation's own `applies_when` gate - the browser must not be
 * the one deciding, or the rule drifts the first time somebody edits it.
 *
 * `enabled` is the dialog being open: 25 product groups on screen would otherwise
 * be 25 requests for lists nobody asked to see.
 */
export function useApplicableSpecKeysQuery(
  productCode: string,
  enabled: boolean,
) {
  return useQuery({
    queryKey: APPLICABLE_KEY(productCode),
    queryFn: () => getApplicableSpecKeys(productCode),
    enabled: enabled && Boolean(productCode),
    staleTime: 60_000,
  });
}
