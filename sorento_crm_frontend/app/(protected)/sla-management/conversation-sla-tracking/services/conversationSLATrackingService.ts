import { apiFetch } from '@/lib/api';
import type { ConversationSLATracking, ConversationSLATrackingDetail, ConversationSLAEventLog, SLATrackingDashboardMetrics } from '../types/conversationSLATracking.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export interface ConversationSLAEventLogsParams {
  tracking_id: string;
  page?: number;
  limit?: number;
  event_type?: string;
  date_from?: string; // YYYY-MM-DD
  date_to?: string;   // YYYY-MM-DD
  assigned_to_id?: string;
}

export interface ConversationSLAEventLogsResponse {
  data: ConversationSLAEventLog[];
  pagination: { total: number; page: number; limit: number };
}

export async function getConversationSLAEventLogs(params: ConversationSLAEventLogsParams): Promise<ConversationSLAEventLogsResponse> {
  const { tracking_id, page = 1, limit = 50, event_type, date_from, date_to, assigned_to_id } = params;
  const queryParams = new URLSearchParams({
    tracking_id,
    page: String(page),
    limit: String(limit),
    ...(event_type ? { event_type } : {}),
    ...(date_from ? { date_from: date_from } : {}),
    ...(date_to ? { date_to: date_to } : {}),
    ...(assigned_to_id ? { assigned_to_id } : {}),
  });
  const response = await apiFetch(`/api/v1/sla-management/conversation-sla-tracking/event-logs?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch event logs');
  return response.json();
}

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

export interface SyncAssigneeResult {
  updated: boolean;
  message: string;
  assigned_to_id?: string;
  assigned_to?: string;
}

export async function syncAssigneeFromRespond(trackingId: string): Promise<SyncAssigneeResult> {
  const response = await apiFetch(`/api/v1/sla-management/conversation-sla-tracking/${trackingId}/sync-assignee`, {
    method: 'POST',
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Sync assignee failed' }));
    const msg = typeof err.detail === 'object' && err.detail?.message ? err.detail.message : err.detail || 'Sync assignee failed';
    throw new Error(msg);
  }
  return response.json();
}

export interface ConversationSLATestOverridesBody {
  assigned_to_id?: string | null;
  current_tier_started_at?: string;
  initiated_at?: string;
  is_responded?: boolean;
  is_resolved?: boolean;
}

export async function postConversationSLATestOverrides(
  trackingId: string,
  body: ConversationSLATestOverridesBody,
): Promise<{ message: string }> {
  const response = await apiFetch(`/api/v1/sla-management/conversation-sla-tracking/${trackingId}/test-overrides`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Update failed' }));
    const detail = err.detail;
    const msg =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join(' ')
          : typeof detail === 'object' && detail !== null && 'message' in detail
            ? String((detail as { message?: string }).message)
            : 'Update failed';
    throw new Error(msg);
  }
  return response.json();
}
