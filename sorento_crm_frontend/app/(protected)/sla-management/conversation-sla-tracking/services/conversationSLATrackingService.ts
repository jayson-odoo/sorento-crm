import { apiFetch } from '@/lib/api';
import type { ConversationSLATracking, ConversationSLATrackingDetail, SLATrackingDashboardMetrics } from '../types/conversationSLATracking.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getConversationSLATracking(params: DataGridApiFetchParams & { policy_id?: string; status?: string; assigned_to?: string }): Promise<DataGridApiResponse<ConversationSLATracking>> {
  const { pageIndex, pageSize, sorting, searchQuery, policy_id, status, assigned_to } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(policy_id ? { policy_id } : {}),
    ...(status ? { status } : {}),
    ...(assigned_to ? { assigned_to } : {}),
  });
  const response = await apiFetch(`/api/v1/sla-management/conversation-sla-tracking?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch conversation SLA tracking');
  return response.json();
}

export async function getConversationSLATrackingDetail(id: string): Promise<ConversationSLATrackingDetail> {
  const response = await apiFetch(`/api/v1/sla-management/conversation-sla-tracking/${id}`);
  if (!response.ok) throw new Error('Failed to fetch conversation SLA tracking detail');
  return response.json();
}

export async function getSLATrackingDashboardMetrics(): Promise<SLATrackingDashboardMetrics> {
  const response = await apiFetch('/api/v1/sla-management/conversation-sla-tracking/dashboard');
  if (!response.ok) throw new Error('Failed to fetch dashboard metrics');
  return response.json();
}

export async function deleteConversationSLATracking(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/sla-management/conversation-sla-tracking/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete conversation SLA tracking');
}

export async function deleteConversationSLAEventLog(logId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/sla-management/conversation-sla-tracking/event-logs/${logId}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to delete event log' }));
    throw new Error(error.detail || 'Failed to delete event log');
  }
}
