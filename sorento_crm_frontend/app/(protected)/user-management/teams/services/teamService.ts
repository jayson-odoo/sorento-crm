import { apiFetch } from '@/lib/api';
import type {
  Team,
  TeamMember,
  TeamCreatePayload,
  TeamUpdatePayload,
  TeamAddMemberPayload,
} from '../types/team.types';

const BASE = '/api/user-management/teams';
const USERS_SELECT = '/api/user-management/users/select';

export interface UserSelectItem {
  id: string;
  name: string | null;
  email: string;
  respond_user_id?: string | null;
  respond_synced?: string | null;
}

/** Fetch users for dropdowns (e.g. add team member). */
export async function getUsersSelect(params?: {
  query?: string;
  respond_synced?: string;
}): Promise<UserSelectItem[]> {
  const sp = new URLSearchParams();
  if (params?.query) sp.set('query', params.query);
  if (params?.respond_synced) sp.set('respond_synced', params.respond_synced);
  const url = USERS_SELECT + (sp.toString() ? `?${sp.toString()}` : '');
  const response = await apiFetch(url);
  if (!response.ok) throw new Error('Failed to fetch users');
  return response.json();
}

export async function getTeams(): Promise<Team[]> {
  const response = await apiFetch(BASE);
  if (!response.ok) throw new Error('Failed to fetch teams');
  return response.json();
}

export async function getTeam(id: string): Promise<Team> {
  const response = await apiFetch(`${BASE}/${id}`);
  if (!response.ok) throw new Error('Failed to fetch team');
  return response.json();
}

export async function createTeam(data: TeamCreatePayload): Promise<Team> {
  const response = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to create team');
  }
  return response.json();
}

export async function updateTeam(id: string, data: TeamUpdatePayload): Promise<Team> {
  const response = await apiFetch(`${BASE}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to update team');
  }
  return response.json();
}

export async function deleteTeam(id: string): Promise<void> {
  const response = await apiFetch(`${BASE}/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to delete team');
  }
}

export async function getTeamMembers(teamId: string): Promise<TeamMember[]> {
  const response = await apiFetch(`${BASE}/${teamId}/members`);
  if (!response.ok) throw new Error('Failed to fetch team members');
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
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to add member');
  }
  return response.json();
}

export async function removeTeamMember(teamId: string, userId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/${teamId}/members/${userId}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to remove member');
  }
}
