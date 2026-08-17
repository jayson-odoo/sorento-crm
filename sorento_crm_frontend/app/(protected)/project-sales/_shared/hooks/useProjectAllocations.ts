'use client';

import { useQuery } from '@tanstack/react-query';
import {
  listAllocationCandidates,
  listAllocationClaims,
  listSalesOrderAllocations,
} from '../services/projectAllocationService';
import type { AllocationClaimListParams } from '../types/projectAllocation.types';

/**
 * Allocation reads only. The supply a line is held by is composed and confirmed in
 * Fulfilment Planning (Stage 1C), in one transaction over the whole sales order, so there
 * is no per-line mutation here and no claim to accept or refuse.
 */

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

/** The Borrows that were written, as audit history (AC-H4). */
export function useAllocationClaims(params: AllocationClaimListParams = {}) {
  return useQuery({
    queryKey: [ALLOCATION_CLAIMS_KEY, params],
    queryFn: () => listAllocationClaims(params),
  });
}
