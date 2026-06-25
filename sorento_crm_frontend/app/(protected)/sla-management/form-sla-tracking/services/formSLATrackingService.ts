import { apiFetch } from '@/lib/api';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type { FormSLATracking } from '../types/formSLATracking.types';

/** Form-SLA tracking list. Same endpoint as conversation SLA, scope=form selects
 *  per-entity form stage rows instead of contact-keyed conversation rows. */
export async function getFormSLATracking(
  params: DataGridApiFetchParams & { policy_id?: string; assigned_to?: string },
): Promise<DataGridApiResponse<FormSLATracking>> {
  const { pageIndex, pageSize, sorting, searchQuery, policy_id, assigned_to } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    scope: 'form',
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(policy_id ? { policy_id } : {}),
    ...(assigned_to ? { assigned_to } : {}),
  });
  const response = await apiFetch(`/api/v1/sla-management/conversation-sla-tracking?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch form SLA tracking');
  return response.json();
}
