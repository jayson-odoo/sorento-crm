import { apiFetch } from '@/lib/api';
import type { SLAPolicy, SLAPolicyFormData, SLAPolicyDetail, SLAPolicyTier, SLAPolicyTierFormData } from '../types/slaPolicy.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getSLAPolicies(params: DataGridApiFetchParams & { status?: string }): Promise<DataGridApiResponse<SLAPolicy>> {
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
  const response = await apiFetch(`/api/v1/sla-management/sla-policies?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch SLA policies');
  return response.json();
}

export async function getSLAPolicy(id: string): Promise<SLAPolicyDetail> {
  const response = await apiFetch(`/api/v1/sla-management/sla-policies/${id}`);
  if (!response.ok) throw new Error('Failed to fetch SLA policy');
  return response.json();
}

export async function createSLAPolicy(data: SLAPolicyFormData): Promise<SLAPolicy> {
  const response = await apiFetch('/api/v1/sla-management/sla-policies', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create SLA policy' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updateSLAPolicy(id: string, data: Partial<SLAPolicyFormData>): Promise<SLAPolicy> {
  const response = await apiFetch(`/api/v1/sla-management/sla-policies/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update SLA policy' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deleteSLAPolicy(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/sla-management/sla-policies/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete SLA policy' }));
    throw new Error(error.message);
  }
}

// SLA Policy Tier methods - Use same path as other SLA; api.ts routes /api/sla-management/ to backend
export async function getSLAPolicyTiers(policyId: string): Promise<SLAPolicyTier[]> {
  const response = await apiFetch(`/api/v1/sla-management/sla-policies/${policyId}/tiers`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to fetch SLA policy tiers' }));
    throw new Error(error.message || 'Failed to fetch SLA policy tiers');
  }
  return response.json();
}

export async function createSLAPolicyTier(policyId: string, data: SLAPolicyTierFormData): Promise<SLAPolicyTier> {
  const response = await apiFetch(`/api/v1/sla-management/sla-policies/${policyId}/tiers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create SLA policy tier' }));
    throw new Error(error.message || 'Failed to create SLA policy tier');
  }
  return response.json();
}

export async function updateSLAPolicyTier(policyId: string, tierId: string, data: Partial<SLAPolicyTierFormData>): Promise<SLAPolicyTier> {
  const response = await apiFetch(`/api/v1/sla-management/sla-policies/${policyId}/tiers/${tierId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update SLA policy tier' }));
    throw new Error(error.message || 'Failed to update SLA policy tier');
  }
  return response.json();
}

export async function deleteSLAPolicyTier(policyId: string, tierId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/sla-management/sla-policies/${policyId}/tiers/${tierId}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete SLA policy tier' }));
    throw new Error(error.message || 'Failed to delete SLA policy tier');
  }
}
