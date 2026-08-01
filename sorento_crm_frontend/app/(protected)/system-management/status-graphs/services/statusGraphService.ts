import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  Status,
  StatusCreateBody,
  StatusEntity,
  StatusGraph,
  StatusMigrateResult,
  StatusTransition,
  StatusUpdateBody,
  TransitionCreateBody,
  TransitionUpdateBody,
} from '../types/statusGraph.types';

const BASE = '/api/v1/system';

export async function listStatusEntities(): Promise<StatusEntity[]> {
  const response = await apiFetch(`${BASE}/status-entities`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load status entities'));
  }
  return response.json();
}

export async function getStatusGraph(
  entityType: string,
  options: { scopeId?: string | null; withCounts?: boolean } = {},
): Promise<StatusGraph> {
  const sp = new URLSearchParams();
  if (options.scopeId) sp.set('scope_id', options.scopeId);
  if (options.withCounts) sp.set('with_counts', 'true');
  const query = sp.toString();
  const response = await apiFetch(
    `${BASE}/statuses/graph/${encodeURIComponent(entityType)}${query ? `?${query}` : ''}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the status graph'));
  }
  return response.json();
}

export async function createStatus(body: StatusCreateBody): Promise<Status> {
  const response = await apiFetch(`${BASE}/statuses`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to create the status'));
  return response.json();
}

export async function updateStatus(id: string, body: StatusUpdateBody): Promise<Status> {
  const response = await apiFetch(`${BASE}/statuses/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to update the status'));
  return response.json();
}

export async function deleteStatus(id: string): Promise<void> {
  const response = await apiFetch(`${BASE}/statuses/${id}`, { method: 'DELETE' });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to delete the status'));
}

export async function migrateStatusRecords(
  id: string,
  toStatusId: string,
): Promise<StatusMigrateResult> {
  const response = await apiFetch(`${BASE}/statuses/${id}/migrate-records`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ to_status_id: toStatusId }),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to move the records'));
  return response.json();
}

export async function createTransition(body: TransitionCreateBody): Promise<StatusTransition> {
  const response = await apiFetch(`${BASE}/status-transitions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to create the transition'));
  }
  return response.json();
}

export async function updateTransition(
  id: string,
  body: TransitionUpdateBody,
): Promise<StatusTransition> {
  const response = await apiFetch(`${BASE}/status-transitions/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to update the transition'));
  }
  return response.json();
}

export async function deleteTransition(id: string): Promise<void> {
  const response = await apiFetch(`${BASE}/status-transitions/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to delete the transition'));
  }
}
