import { apiFetch } from '@/lib/api';
import { extractApiError, buildDataGridParams } from '@/lib/api-client';
import type { AccessAgent, AccessAgentFormData, AccessAgentDetail, ContactAgentAccess, ContactAgentAccessFormData, RespondSyncedUser } from '../types/accessAgent.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import { getUsersSelect } from '@/services/userSelectService';
import { getTeams } from '@/app/(protected)/user-management/teams/services/teamService';

export async function getAccessAgents(params: DataGridApiFetchParams & { status?: string }): Promise<DataGridApiResponse<AccessAgent>> {
  const queryParams = buildDataGridParams(params, { status: params.status });
  const response = await apiFetch(`/api/user-management/access-agents?${queryParams.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to fetch access agents'));
  return response.json();
}

export async function getAccessAgent(id: string): Promise<AccessAgentDetail> {
  const response = await apiFetch(`/api/user-management/access-agents/${id}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to fetch access agent'));
  return response.json();
}

export async function createAccessAgent(data: AccessAgentFormData): Promise<AccessAgent> {
  const response = await apiFetch('/api/user-management/access-agents', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to create access agent'));
  return response.json();
}

export async function updateAccessAgent(id: string, data: Partial<AccessAgentFormData>): Promise<AccessAgent> {
  const response = await apiFetch(`/api/user-management/access-agents/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to update access agent'));
  return response.json();
}

export async function getRespondSyncedUsers(query?: string): Promise<RespondSyncedUser[]> {
  return getUsersSelect({ respond_synced: 'successful', query });
}

export async function deleteAccessAgent(id: string): Promise<void> {
  const response = await apiFetch(`/api/user-management/access-agents/${id}`, { method: 'DELETE' });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to delete access agent'));
}

// Contact Agent Access methods
export async function getContactAccessAgents(agentId: string): Promise<ContactAgentAccess[]> {
  const response = await apiFetch(`/api/user-management/access-agents/${agentId}/contact-access`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to fetch contact access agents'));
  return response.json();
}

export async function createContactAgentAccess(agentId: string, data: ContactAgentAccessFormData): Promise<ContactAgentAccess> {
  const response = await apiFetch(`/api/user-management/access-agents/${agentId}/contact-access`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const msg = await extractApiError(response, 'Failed to create contact access agent');
    if (response.status === 409 || msg.toLowerCase().includes('duplicate') || msg.toLowerCase().includes('already exists')) {
      throw new Error('An access agent entry already exists for this contact and agent combination.');
    }
    throw new Error(msg);
  }
  return response.json();
}

export async function updateContactAgentAccess(agentId: string, contactId: string, data: Partial<ContactAgentAccessFormData>): Promise<ContactAgentAccess> {
  const response = await apiFetch(`/api/user-management/access-agents/${agentId}/contact-access/${contactId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to update contact access agent'));
  return response.json();
}

export async function deleteContactAgentAccess(agentId: string, contactId: string): Promise<void> {
  const response = await apiFetch(`/api/user-management/access-agents/${agentId}/contact-access/${contactId}`, { method: 'DELETE' });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to delete contact access agent'));
}

// Agent team assignments (code -> team for round-robin next-assignee)
export interface AgentTeamMemberInfo {
  id: string;
  name: string | null;
  email: string | null;
}

export interface AgentTeamAssignment {
  code: string;
  team_id: string;
  team_name?: string;
  members?: AgentTeamMemberInfo[];
  last_assigned?: AgentTeamMemberInfo | null;
  next_in_line?: AgentTeamMemberInfo | null;
}

export async function getAgentTeams(agentId: string): Promise<{ assignments: AgentTeamAssignment[] }> {
  const response = await apiFetch(`/api/user-management/access-agents/${agentId}/teams`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to fetch agent teams'));
  const data = await response.json();
  return { assignments: data.assignments ?? [] };
}

export async function setAgentTeams(
  agentId: string,
  assignments: AgentTeamAssignment[],
): Promise<{ assignments: AgentTeamAssignment[] }> {
  const response = await apiFetch(`/api/user-management/access-agents/${agentId}/teams`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ assignments }),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to set agent teams'));
  return response.json();
}

export type { Team } from '@/app/(protected)/user-management/teams/types/team.types';
export { getTeams };
