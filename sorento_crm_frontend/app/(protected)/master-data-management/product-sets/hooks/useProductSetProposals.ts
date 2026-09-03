import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  applyProductSetProposals,
  getProductSetProposals,
  runProductSetProposals,
} from '../services/productSetProposalService';

const KEY = ['product-set-proposals'];

export function useProductSetProposals() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => getProductSetProposals(),
    retry: 1,
  });
}

export function useRunProductSetProposals() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => runProductSetProposals(),
    onSuccess: (batch) => {
      queryClient.setQueryData(KEY, batch);
      toast.success(
        batch.proposal_count === 0
          ? 'No new sets to propose - every family the catalogue names already has one'
          : `${batch.proposal_count} set${batch.proposal_count === 1 ? '' : 's'} proposed across ${batch.family_count} famil${batch.family_count === 1 ? 'y' : 'ies'}`,
      );
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to propose sets'),
  });
}

export function useApplyProductSetProposals() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (proposalIds: string[]) => applyProductSetProposals(proposalIds),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: KEY });
      queryClient.invalidateQueries({ queryKey: ['product-sets'] });
      if (result.applied.length) {
        toast.success(
          `${result.applied.length} set${result.applied.length === 1 ? '' : 's'} created`,
        );
      }
      // A refusal is named, never swallowed: the reviewer ticked it and has to
      // learn why it did not land.
      for (const refusal of result.refused) {
        toast.error(`${refusal.set_code} was not created: ${refusal.reason}`);
      }
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create the sets'),
  });
}
