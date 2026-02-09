import { apiFetch } from '@/lib/api';
import type { AccessAgent, AccessAgentFormData, AccessAgentDetail, ContactAgentAccess, ContactAgentAccessFormData, RespondSyncedUser } from '../types/accessAgent.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getAccessAgents(params: DataGridApiFetchParams & { status?: string }): Promise<DataGridApiResponse<AccessAgent>> {
  const { pageIndex, pageSize, sorting, searchQuery, status } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(status ? { status } : {}),
  });
  const response = await apiFetch(`/api/user-management/access-agents?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch access agents');
  return response.json();
}

export async function getAccessAgent(id: string): Promise<AccessAgentDetail> {
  const response = await apiFetch(`/api/user-management/access-agents/${id}`);
  if (!response.ok) throw new Error('Failed to fetch access agent');
  return response.json();
}

export async function createAccessAgent(data: AccessAgentFormData): Promise<AccessAgent> {
  const response = await apiFetch('/api/user-management/access-agents', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create access agent' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updateAccessAgent(id: string, data: Partial<AccessAgentFormData>): Promise<AccessAgent> {
  const response = await apiFetch(`/api/user-management/access-agents/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update access agent' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function getRespondSyncedUsers(query?: string): Promise<RespondSyncedUser[]> {
  const queryParams = new URLSearchParams({
    respond_synced: 'successful',
    ...(query ? { query } : {}),
  });
  const response = await apiFetch(`/api/user-management/users/select?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch respond synced users');
  return response.json();
}

export async function deleteAccessAgent(id: string): Promise<void> {
  const response = await apiFetch(`/api/user-management/access-agents/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete access agent' }));
    throw new Error(error.message);
  }
}

// Contact Agent Access methods
export async function getContactAccessAgents(agentId: string): Promise<ContactAgentAccess[]> {
  const response = await apiFetch(`/api/user-management/access-agents/${agentId}/contact-access`);
  if (!response.ok) throw new Error('Failed to fetch contact access agents');
  return response.json();
}

export async function createContactAgentAccess(agentId: string, data: ContactAgentAccessFormData): Promise<ContactAgentAccess> {
  const response = await apiFetch(`/api/user-management/access-agents/${agentId}/contact-access`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create contact access agent' }));
    // Handle duplicate/conflict errors specifically
    if (response.status === 409 || error.message?.toLowerCase().includes('duplicate') || error.message?.toLowerCase().includes('already exists')) {
      throw new Error('An access agent entry already exists for this contact and agent combination.');
    }
    throw new Error(error.detail?.message || error.message || 'Failed to create contact access agent');
  }
  return response.json();
}

export async function updateContactAgentAccess(agentId: string, contactId: string, data: Partial<ContactAgentAccessFormData>): Promise<ContactAgentAccess> {
  const response = await apiFetch(`/api/user-management/access-agents/${agentId}/contact-access/${contactId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update contact access agent' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deleteContactAgentAccess(agentId: string, contactId: string): Promise<void> {
  const response = await apiFetch(`/api/user-management/access-agents/${agentId}/contact-access/${contactId}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete contact access agent' }));
    throw new Error(error.message);
  }
}
