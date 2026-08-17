import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  AllocationCandidateList,
  AllocationClaimBody,
  AllocationClaimListParams,
  AllocationClaimRow,
  AllocationConfirmBody,
  AllocationLineRow,
} from '../types/projectAllocation.types';

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

export async function confirmAllocation(
  lineId: string,
  body: AllocationConfirmBody,
): Promise<AllocationLineRow> {
  const response = await apiFetch(`${BASE}/sales-order-lines/${lineId}/allocation`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to save the source'));
  return response.json();
}

export async function clearAllocation(lineId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/sales-order-lines/${lineId}/allocation`, {
    method: 'DELETE',
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to clear the source'));
}

/** Ask the holding project's CS for stock. Grants nothing until they answer (AC-H4). */
export async function raiseAllocationClaim(
  lineId: string,
  body: AllocationClaimBody,
): Promise<AllocationClaimRow> {
  const response = await apiFetch(`${BASE}/sales-order-lines/${lineId}/allocation-claims`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to raise the claim'));
  return response.json();
}

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

export async function acceptAllocationClaim(claimId: string): Promise<AllocationClaimRow> {
  const response = await apiFetch(`${BASE}/allocation-claims/${claimId}/accept`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to release the stock'));
  return response.json();
}

/** A refusal always carries a reason. The backend rejects a blank one. */
export async function refuseAllocationClaim(
  claimId: string,
  reason: string,
): Promise<AllocationClaimRow> {
  const response = await apiFetch(`${BASE}/allocation-claims/${claimId}/refuse`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to refuse the claim'));
  return response.json();
}
