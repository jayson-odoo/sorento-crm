'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  acceptAllocationClaim,
  clearAllocation,
  confirmAllocation,
  listAllocationCandidates,
  listAllocationClaims,
  listSalesOrderAllocations,
  raiseAllocationClaim,
  refuseAllocationClaim,
} from '../services/projectAllocationService';
import type {
  AllocationClaimBody,
  AllocationClaimListParams,
  AllocationConfirmBody,
} from '../types/projectAllocation.types';

export const ALLOCATIONS_KEY = 'project-so-allocations';
export const ALLOCATION_CANDIDATES_KEY = 'project-allocation-candidates';
export const ALLOCATION_CLAIMS_KEY = 'project-allocation-claims';

export const allocationsKey = (psoId: string) => [ALLOCATIONS_KEY, psoId];
export const allocationCandidatesKey = (lineId: string) => [ALLOCATION_CANDIDATES_KEY, lineId];

export function useSalesOrderAllocations(psoId: string | undefined) {
  return useQuery({
    queryKey: allocationsKey(psoId ?? ''),
    queryFn: () => listSalesOrderAllocations(psoId as string),
    enabled: Boolean(psoId),
  });
}

/**
 * Ranked sources for one line.
 *
 * `staleTime: 0` and no window-focus reuse on purpose: these figures belong to other
 * people's stock and go stale the moment they ship. The query only runs while the picker
 * that shows them is open.
 */
export function useAllocationCandidates(lineId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: allocationCandidatesKey(lineId ?? ''),
    queryFn: () => listAllocationCandidates(lineId as string),
    enabled: Boolean(lineId) && enabled,
    staleTime: 0,
    gcTime: 0,
  });
}

export function useAllocationClaims(params: AllocationClaimListParams = {}) {
  return useQuery({
    queryKey: [ALLOCATION_CLAIMS_KEY, params],
    queryFn: () => listAllocationClaims(params),
  });
}

/** Everything that writes to one order's allocation. */
export function useAllocationMutations(psoId: string) {
  const queryClient = useQueryClient();
  const invalidate = (lineId?: string) => {
    queryClient.invalidateQueries({ queryKey: allocationsKey(psoId) });
    queryClient.invalidateQueries({ queryKey: [ALLOCATION_CLAIMS_KEY] });
    if (lineId) queryClient.invalidateQueries({ queryKey: allocationCandidatesKey(lineId) });
  };

  const confirm = useMutation({
    mutationFn: ({ lineId, body }: { lineId: string; body: AllocationConfirmBody }) =>
      confirmAllocation(lineId, body),
    onSuccess: (row) => {
      invalidate(row.line_id);
      toast.success(
        row.stock_location ? `Source set to ${row.stock_location}` : 'Source recorded',
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const clear = useMutation({
    mutationFn: (lineId: string) => clearAllocation(lineId),
    onSuccess: (_result, lineId) => {
      invalidate(lineId);
      toast.success('Source cleared');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const claim = useMutation({
    mutationFn: ({ lineId, body }: { lineId: string; body: AllocationClaimBody }) =>
      raiseAllocationClaim(lineId, body),
    onSuccess: (row, variables) => {
      invalidate(variables.lineId);
      toast.success(
        `${row.to_project_code} asked for ${row.qty}. Nothing moves until they answer.`,
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { confirm, clear, claim };
}

/** The claims inbox: accept releases the stock, refuse always carries a reason. */
export function useAllocationClaimMutations() {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: [ALLOCATION_CLAIMS_KEY] });
    queryClient.invalidateQueries({ queryKey: [ALLOCATIONS_KEY] });
  };

  const accept = useMutation({
    mutationFn: (claimId: string) => acceptAllocationClaim(claimId),
    onSuccess: (row) => {
      invalidate();
      toast.success(`Released to ${row.from_project_code}`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const refuse = useMutation({
    mutationFn: ({ claimId, reason }: { claimId: string; reason: string }) =>
      refuseAllocationClaim(claimId, reason),
    onSuccess: (row) => {
      invalidate();
      toast.success(`Refused. ${row.from_project_code} has been told why.`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { accept, refuse };
}
