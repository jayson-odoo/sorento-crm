import { apiFetch } from '@/lib/api';
import type { ConversationSLAEventLog } from '../types/eventLog.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getEventLogs(
  params: DataGridApiFetchParams & { tracking_id?: string; event_type?: string; assigned_to?: string },
): Promise<DataGridApiResponse<ConversationSLAEventLog>> {
  const { pageIndex, pageSize, sorting, tracking_id, event_type, assigned_to } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(tracking_id ? { tracking_id } : {}),
    ...(event_type ? { event_type } : {}),
    ...(assigned_to ? { assigned_to } : {}),
  });
  const response = await apiFetch(
    `/api/sla-management/conversation-sla-tracking/event-logs?${queryParams.toString()}`,
  );
  if (!response.ok) throw new Error('Failed to fetch SLA event logs');
  return response.json();
}
