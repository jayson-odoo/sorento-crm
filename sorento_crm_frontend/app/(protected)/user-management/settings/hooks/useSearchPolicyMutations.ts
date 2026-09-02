'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { updateSearchPolicy } from '@/app/(protected)/master-data-management/product-specifications/services/productSpecService';
import { SEARCH_POLICY_QUERY_KEY } from './useSearchPolicyQuery';

/**
 * Saves one ranking knob at a time (AC-C.1: per-row Save, not a form submit).
 * `save.variables` after a call carries the `policyKey` that is in flight, so a row
 * can tell whether it is the one saving without a state array of its own.
 */
export function useSearchPolicyMutations() {
  const queryClient = useQueryClient();

  const save = useMutation({
    mutationFn: ({ policyKey, value }: { policyKey: string; value: number }) =>
      updateSearchPolicy(policyKey, value),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: SEARCH_POLICY_QUERY_KEY });
      toast.success('Search ranking saved');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to save the search setting');
    },
  });

  return { save };
}
