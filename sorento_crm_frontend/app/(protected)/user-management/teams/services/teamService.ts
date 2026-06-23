import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import { getUsersSelect } from '@/services/userSelectService';
import type {
  Team,
  TeamMember,
  TeamCreatePayload,
  TeamUpdatePayload,
  TeamAddMemberPayload,
  TeamMemberUpdatePayload,
} from '../types/team.types';

export type { UserSelectItem } from '@/services/userSelectService';
export { getUsersSelect };

const BASE = '/api/user-management/teams';

export async function getTeams(): Promise<Team[]> {
  const response = await apiFetch(BASE);
  if (!response.ok) throw new Error('Failed to fetch teams');
  return response.json();
}

export async function getTeam(id: string): Promise<Team> {
  const response = await apiFetch(`${BASE}/${id}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to fetch team'));
  return response.json();
}

export async function createTeam(data: TeamCreatePayload): Promise<Team> {
  const response = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to create team'));
  return response.json();
}

export async function updateTeam(id: string, data: TeamUpdatePayload): Promise<Team> {
  const response = await apiFetch(`${BASE}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to update team'));
  return response.json();
}

export async function deleteTeam(id: string): Promise<void> {
  const response = await apiFetch(`${BASE}/${id}`, { method: 'DELETE' });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to delete team'));
}

export async function getTeamMembers(teamId: string): Promise<TeamMember[]> {
  const response = await apiFetch(`${BASE}/${teamId}/members`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to fetch team members'));
  return response.json();
}

export async function addTeamMember(
  teamId: string,
  data: TeamAddMemberPayload,
): Promise<TeamMember> {
  const response = await apiFetch(`${BASE}/${teamId}/members`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to add member'));
  return response.json();
}

export async function removeTeamMember(teamId: string, userId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/${teamId}/members/${userId}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to remove member'));
}

export async function updateTeamMember(
  teamId: string,
  userId: string,
  data: TeamMemberUpdatePayload,
): Promise<TeamMember> {
  const response = await apiFetch(`${BASE}/${teamId}/members/${userId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to update member'));
  return response.json();
}
