import { apiFetch } from '@/lib/api';
import type { Campaign, CampaignFormData, CampaignDetail, CampaignType } from '../types/campaign.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getCampaigns(params: DataGridApiFetchParams & { campaign_type_id?: string; status?: string; date_from?: string; date_to?: string; budget_min?: number; budget_max?: number }): Promise<DataGridApiResponse<Campaign>> {
  const { pageIndex, pageSize, sorting, searchQuery, campaign_type_id, status, date_from, date_to, budget_min, budget_max } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(campaign_type_id ? { campaign_type_id } : {}),
    ...(status ? { status } : {}),
    ...(date_from ? { date_from } : {}),
    ...(date_to ? { date_to } : {}),
    ...(budget_min ? { budget_min: String(budget_min) } : {}),
    ...(budget_max ? { budget_max: String(budget_max) } : {}),
  });
  const response = await apiFetch(`/api/marketing/campaigns?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch campaigns');
  return response.json();
}

export async function getCampaign(id: string): Promise<CampaignDetail> {
  const response = await apiFetch(`/api/marketing/campaigns/${id}`);
  if (!response.ok) throw new Error('Failed to fetch campaign');
  return response.json();
}

export async function getCampaignTypes(): Promise<CampaignType[]> {
  const response = await apiFetch('/api/marketing/campaign-types');
  if (!response.ok) throw new Error('Failed to fetch campaign types');
  return response.json();
}

export async function createCampaign(data: CampaignFormData): Promise<Campaign> {
  const response = await apiFetch('/api/marketing/campaigns', {
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
  const response = await apiFetch(`/api/marketing/campaigns/${id}`, {
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
  const response = await apiFetch(`/api/marketing/campaigns/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete campaign' }));
    throw new Error(error.message);
  }
}
