import { apiFetch } from '@/lib/api';
import type { ContactAccessAgent } from '../types/contactAccessAgent.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getContactAccessAgents(params: DataGridApiFetchParams & { agent_id?: string; contact_id?: string }): Promise<DataGridApiResponse<ContactAccessAgent>> {
  const { pageIndex, pageSize, sorting, searchQuery, agent_id, contact_id } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(agent_id ? { agent_id } : {}),
    ...(contact_id ? { contact_id } : {}),
  });
  const response = await apiFetch(`/api/user-management/contact-access-agents?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch contact access agents');
  return response.json();
}
