/**
 * Sales teams - feature service (plan 3.8).
 *
 * Layering: components -> hooks (useSalesTeams) -> THIS service -> lib/api.
 *
 * Backend contract (module `sales`, mounted at /api/v1/sales behind its module guard):
 *   GET    /sales/teams?query            -> { data: SalesTeamListItem[], pagination, empty }  sales.teams.view
 *   GET    /sales/teams/agent-options    -> { data: SalesTeamAgentOption[] }                  sales.teams.view
 *   GET    /sales/teams/{id}?on          -> SalesTeamDetail                                   sales.teams.view
 *   POST   /sales/teams                  body SalesTeamCreatePayload -> SalesTeamDetail       sales.teams.add
 *   PATCH  /sales/teams/{id}             body SalesTeamUpdatePayload -> SalesTeamDetail       sales.teams.edit
 *          (name, Active and optionally the agents with moves_on, in one transaction)
 *   PUT    /sales/teams/{id}/members     body SalesTeamMembersPayload -> SalesTeamDetail      sales.teams.edit
 * Delete is the parked action `sales_team.delete` (D7), through useDeferredAction.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  SalesTeamAgentOption,
  SalesTeamCreatePayload,
  SalesTeamDetail,
  SalesTeamListItem,
  SalesTeamMembersPayload,
  SalesTeamUpdatePayload,
} from '../types/salesTeam.types';

const BASE = '/api/v1/sales/teams';

export interface SalesTeamListResponse {
  data: SalesTeamListItem[];
  pagination: { total: number; page: number; limit: number };
  empty: boolean;
}

async function read<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) throw new Error(await extractApiError(response, fallback));
  return response.json();
}

function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
}

export async function getSalesTeams(query: string): Promise<SalesTeamListResponse> {
  const q = query.trim();
  const url = q ? `${BASE}?${new URLSearchParams({ query: q }).toString()}` : BASE;
  return read(await apiFetch(url), 'Failed to load sales teams');
}

export async function getSalesTeam(id: string, on?: string): Promise<SalesTeamDetail> {
  const url = on ? `${BASE}/${id}?${new URLSearchParams({ on }).toString()}` : `${BASE}/${id}`;
  return read(await apiFetch(url), 'Failed to load sales team');
}

export async function getSalesTeamAgentOptions(): Promise<SalesTeamAgentOption[]> {
  const body = await read<{ data: SalesTeamAgentOption[] }>(
    await apiFetch(`${BASE}/agent-options`),
    'Failed to load sales agents',
  );
  return body.data;
}

export async function createSalesTeam(payload: SalesTeamCreatePayload): Promise<SalesTeamDetail> {
  return read(await apiFetch(BASE, jsonInit('POST', payload)), 'Failed to create sales team');
}

export async function updateSalesTeam(
  id: string,
  payload: SalesTeamUpdatePayload,
): Promise<SalesTeamDetail> {
  return read(await apiFetch(`${BASE}/${id}`, jsonInit('PATCH', payload)), 'Failed to save sales team');
}

export async function setSalesTeamMembers(
  id: string,
  payload: SalesTeamMembersPayload,
): Promise<SalesTeamDetail> {
  return read(
    await apiFetch(`${BASE}/${id}/members`, jsonInit('PUT', payload)),
    'Failed to save the team agents',
  );
}
