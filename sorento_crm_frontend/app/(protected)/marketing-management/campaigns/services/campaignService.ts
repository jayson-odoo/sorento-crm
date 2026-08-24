import { apiFetch } from '@/lib/api';
import type { Campaign, CampaignFormData, CampaignDetail, CampaignType } from '../types/campaign.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

// NOTE: only `status` is filterable server-side. The campaign_type/date/budget
// filter params the FE used to send were never honoured by `list_campaigns`
// (dead controls) and were removed - re-add here AND in the BE service together
// if real type/date/budget filtering is wanted (see PLAN-fix-security-cluster C2).
export async function getCampaigns(params: DataGridApiFetchParams & { status?: string }): Promise<DataGridApiResponse<Campaign>> {
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
  const response = await apiFetch(`/api/v1/marketing/campaigns?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch campaigns');
  return response.json();
}

export async function getCampaign(id: string): Promise<CampaignDetail> {
  const response = await apiFetch(`/api/v1/marketing/campaigns/${id}`);
  if (!response.ok) throw new Error('Failed to fetch campaign');
  return response.json();
}

export async function getCampaignTypes(): Promise<CampaignType[]> {
  const response = await apiFetch('/api/v1/marketing/campaign-types');
  if (!response.ok) throw new Error('Failed to fetch campaign types');
  // Endpoint returns a paginated envelope `{ data: [...] }`, not a bare array.
  const body = await response.json();
  return Array.isArray(body) ? body : (body?.data ?? []);
}

export async function createCampaign(data: CampaignFormData): Promise<Campaign> {
  // Trailing slash matches the FastAPI route exactly - without it the POST 307s
  // to `/campaigns/` and the cross-origin redirect drops the CORS header.
  const response = await apiFetch('/api/v1/marketing/campaigns/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create campaign' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updateCampaign(id: string, data: Partial<CampaignFormData>): Promise<Campaign> {
  const response = await apiFetch(`/api/v1/marketing/campaigns/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update campaign' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deleteCampaign(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/marketing/campaigns/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete campaign' }));
    throw new Error(error.message);
  }
}
