import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  AllocationCandidateList,
  AllocationClaimListParams,
  AllocationClaimRow,
  AllocationLineRow,
} from '../types/projectAllocation.types';

/**
 * Allocation READS (P9), and nothing else.
 *
 * Stage 1C moved the writing: a Project SO's supply is composed and committed in ONE
 * atomic transaction in Fulfilment Planning, so per-line confirmation, clearing a line's
 * source, and the raise / accept / refuse claim handshake are gone from the backend and
 * from here. A cross-project Borrow is written straight to `accepted` inside that same
 * transaction by the CS actor who confirms, which is why there is nothing left to answer.
 *
 * What survives is what the supply sheet and its audit read: the ranked candidates it
 * offers as Borrow sources, the components of an order's active decision, and the claims
 * history.
 */

const BASE = '/api/v1/project-sales';

export interface AllocationListEnvelope<T> {
  data: T[];
  total: number;
  page: number;
  limit: number;
}

function normaliseEnvelope<T>(body: unknown, fallbackLimit: number): AllocationListEnvelope<T> {
  const raw = (body ?? {}) as {
    data?: T[];
    pagination?: { total?: number; page?: number; limit?: number };
  };
  const rows = Array.isArray(raw.data) ? raw.data : [];
  return {
    data: rows,
    total: raw.pagination?.total ?? rows.length,
    page: raw.pagination?.page ?? 1,
    limit: raw.pagination?.limit ?? fallbackLimit,
  };
}

/** Every line on the order and where it is coming from, sourced or not. */
export async function listSalesOrderAllocations(
  psoId: string,
): Promise<AllocationListEnvelope<AllocationLineRow>> {
  const response = await apiFetch(`${BASE}/sales-orders/${psoId}/allocations`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the allocation'));
  return normaliseEnvelope<AllocationLineRow>(await response.json(), 100);
}

/**
 * The ranked sources for one line, computed live by the backend on every call.
 *
 * Never cached beyond the moment it is shown: acting on another project's stale on-hand
 * is the failure this whole surface exists to prevent.
 */
export async function listAllocationCandidates(
  lineId: string,
): Promise<AllocationCandidateList> {
  const response = await apiFetch(`${BASE}/sales-order-lines/${lineId}/allocation-candidates`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the ranked sources'));
  return response.json();
}

/** The Borrows that were written, as audit history. Nothing here is answered. */
export async function listAllocationClaims(
  params: AllocationClaimListParams = {},
): Promise<AllocationListEnvelope<AllocationClaimRow>> {
  const limit = params.limit ?? 50;
  const search = new URLSearchParams();
  search.set('direction', params.direction ?? 'incoming');
  search.set('page', String(params.page ?? 1));
  search.set('limit', String(limit));
  (params.state ?? []).forEach((state) => search.append('state', state));
  const response = await apiFetch(`${BASE}/allocation-claims?${search.toString()}`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the stock claims'));
  return normaliseEnvelope<AllocationClaimRow>(await response.json(), limit);
}
