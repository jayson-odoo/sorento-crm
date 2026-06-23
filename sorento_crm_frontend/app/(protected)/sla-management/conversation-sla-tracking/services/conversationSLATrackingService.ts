import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { RespondConversationResponse } from '@/app/(protected)/procurement-management/stock-inquiries/services/stockInquiryService';
import type { ConversationSLATracking, ConversationSLATrackingDetail, ConversationSLAEventLog, SLATrackingDashboardMetrics } from '../types/conversationSLATracking.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export interface ConversationSLAEventLogsParams {
  tracking_id: string;
  page?: number;
  limit?: number;
  sort?: string;
  dir?: 'asc' | 'desc';
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
  const { tracking_id, page = 1, limit = 50, sort = 'event_at', dir = 'desc', event_type, date_from, date_to, assigned_to_id } = params;
  const queryParams = new URLSearchParams({
    tracking_id,
    page: String(page),
    limit: String(limit),
    sort,
    dir,
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

/** A pending (or just-resolved) takeover attached to an SLA row. Drives the countdown
 *  bar, the Cancel/Reject affordances, and the contested-task banner. */
export interface TakeoverInfo {
  request_id: string;
  tracking_id: string;
  initiator_id: string;
  initiator_name: string;
  contested_assignee_id: string | null;
  contested_assignee_name: string | null;
  team_id: string | null;
  status: 'pending' | 'committed' | 'cancelled' | 'rejected' | 'voided';
  /** Absolute ISO timestamp the takeover commits — drives the countdown locally. */
  commit_at: string | null;
  /** Total cooldown window in seconds — fixed bar denominator (survives remounts). */
  window_seconds?: number | null;
  resolution_reason: string | null;
  /** Viewer-relative (server-computed): initiator/admin can cancel; owner/admin can reject. */
  can_cancel?: boolean;
  can_reject?: boolean;
}

export interface MyPendingSLAItem {
  id: string;
  source_entity_type: string | null;
  source_entity_id: string | null;
  /** Authoritative form-vs-conversation flag from the backend (FORM_SLA_TYPES).
   *  Conversation rows = false. The widget must use this, not re-derive from routes. */
  is_form_sla: boolean;
  /** Human-readable reference: complaint/inquiry/request/ticket number, or contact name. */
  reference: string | null;
  /** Respond.io contact id for conversation rows; used to build the inbox deep link. */
  respond_io_id: string | null;
  /** SLA-config-driven next action for form rows (e.g. "Send for approval"); null for conversation rows. */
  next_action: string | null;
  due_at: string | null;
  is_responded: boolean;
  current_tier: number;
  policy_name: string | null;
  /** Pending takeover on this row, if any (inline "being taken over" indicator). */
  takeover?: TakeoverInfo | null;
}

export async function getMyPendingSLA(limit = 50): Promise<MyPendingSLAItem[]> {
  const response = await apiFetch(
    `/api/v1/sla-management/conversation-sla-tracking/my-pending?limit=${limit}`,
  );
  if (!response.ok) throw new Error('Failed to fetch my pending SLAs');
  const body = await response.json();
  return Array.isArray(body?.data) ? (body.data as MyPendingSLAItem[]) : [];
}

/**
 * Resolve a conversation SLA tracking row (assignee action). Flips is_resolved;
 * the backend also best-effort closes the matching Respond.io conversation.
 */
export async function resolveConversationSLATracking(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/sla-management/conversation-sla-tracking/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ is_resolved: true }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to resolve conversation SLA'));
  }
}

/**
 * Manually escalate a conversation SLA tracking row to the next tier with a reason.
 * Stored as "manual: <reason>"; reassigns + notifies per policy. Capped at tier 3.
 */
export async function escalateConversationSLATracking(id: string, reason: string): Promise<void> {
  const response = await apiFetch(`/api/v1/sla-management/conversation-sla-tracking/${id}/escalate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to escalate conversation SLA'));
  }
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

export async function getSlaTrackingConversation(
  trackingId: string,
  params?: { limit?: number; cursor?: string },
): Promise<RespondConversationResponse> {
  const sp = new URLSearchParams();
  if (params?.limit != null) sp.set('limit', String(params.limit));
  if (params?.cursor) sp.set('cursor', params.cursor);
  const qs = sp.toString();
  const url = `/api/v1/sla-management/conversation-sla-tracking/${trackingId}/conversation${qs ? `?${qs}` : ''}`;
  const response = await apiFetch(url);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || err.message || 'Failed to load conversation');
  }
  return response.json();
}

// ---------------------------------------------------------------------------
// My Team Tasks / Takeover / Reassign (team coverage & reassignment)
// ---------------------------------------------------------------------------

/** One visible-team pending SLA task. Names are resolved server-side (no UUIDs in UI). */
export interface TeamPendingItem {
  id: string;
  assignee_id: string;
  assignee_name: string;
  team_id: string;
  team_label: string;
  source_entity_type: string | null;
  source_entity_id: string | null;
  is_form_sla: boolean;
  reference: string | null;
  due_at: string | null;
  is_responded: boolean;
  current_tier: number;
  policy_name: string | null;
  next_action: string | null;
  /** Pending takeover on this row (running bar / observer-locked state). */
  takeover?: TakeoverInfo | null;
}

export interface TeamPendingResponse {
  data: TeamPendingItem[];
  total: number;
  page: number;
  limit: number;
  empty: boolean;
}

export interface TeamPendingFilters {
  page?: number;
  limit?: number;
  assignee?: string;
  team?: string;
  query?: string;
}

/** Visible-team pending tasks (peers + descendant teams), excluding my own. */
export async function getTeamPendingSLA(filters: TeamPendingFilters = {}): Promise<TeamPendingResponse> {
  const { page = 1, limit = 50, assignee, team, query } = filters;
  const params = buildDataGridParams(
    { pageIndex: page - 1, pageSize: limit },
    { assignee, team, ...(query ? { query } : {}) },
  );
  const response = await apiFetch(
    `/api/v1/sla-management/conversation-sla-tracking/team-pending?${params.toString()}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to fetch team tasks'));
  }
  return response.json();
}

/** Scope-B user picker source (members of teams I can see, excluding me). */
export interface VisibleUser {
  id: string;
  name: string;
  email: string;
}

export async function getVisibleUsers(): Promise<VisibleUser[]> {
  const response = await apiFetch(
    '/api/v1/sla-management/conversation-sla-tracking/visible-users',
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to fetch visible users'));
  }
  const body = await response.json();
  return Array.isArray(body?.data) ? (body.data as VisibleUser[]) : [];
}

/** Result of initiating a takeover. With a cooldown configured the takeover is
 *  PENDING (a veto window); cooldown 0 or an unassigned task commits instantly. */
export interface TakeoverInitiateResult {
  committed: boolean;
  request?: TakeoverInfo;
  /** True when a takeover was already pending — `request` is the existing one (bar resumes). */
  already_pending?: boolean;
}

/** Initiate a takeover. 409 (already pending) is NOT an error — the existing request
 *  is returned so the UI shows the running countdown. */
export async function takeoverSLATracking(
  id: string,
  teamId: string,
): Promise<TakeoverInitiateResult> {
  const response = await apiFetch(
    `/api/v1/sla-management/conversation-sla-tracking/${id}/takeover`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ team_id: teamId }),
    },
  );
  if (response.status === 409) {
    const body = await response.json().catch(() => ({}));
    return { committed: false, already_pending: true, request: body?.request };
  }
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to take over task'));
  }
  return response.json();
}

/** Initiator (or admin) withdraws a pending takeover. */
export async function cancelTakeover(requestId: string): Promise<TakeoverInfo> {
  const response = await apiFetch(
    `/api/v1/sla-management/conversation-sla-tracking/takeover-requests/${requestId}/cancel`,
    { method: 'POST' },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to cancel takeover'));
  }
  return response.json();
}

/** Contested assignee (or admin) vetoes a pending takeover. */
export async function rejectTakeover(requestId: string): Promise<TakeoverInfo> {
  const response = await apiFetch(
    `/api/v1/sla-management/conversation-sla-tracking/takeover-requests/${requestId}/reject`,
    { method: 'POST' },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to reject takeover'));
  }
  return response.json();
}

/** Pin-fetch a single contested task + its latest takeover, for the My Pending banner. */
export interface TakeoverStateRow {
  id: string;
  source_entity_type: string | null;
  source_entity_id: string | null;
  is_form_sla: boolean;
  reference: string | null;
  due_at: string | null;
  current_tier: number | null;
  is_resolved: boolean;
  assigned_to_id: string | null;
  takeover: TakeoverInfo | null;
}

export async function getTakeoverState(trackingId: string): Promise<TakeoverStateRow> {
  const response = await apiFetch(
    `/api/v1/sla-management/conversation-sla-tracking/${trackingId}/takeover-state`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load takeover'));
  }
  return response.json();
}

/** Hand a task to a chosen user, keeping the original team/tier/clock. */
export async function reassignSLATracking(id: string, userId: string): Promise<void> {
  const response = await apiFetch(
    `/api/v1/sla-management/conversation-sla-tracking/${id}/reassign`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId }),
    },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to reassign task'));
  }
}

export async function postSlaTrackingConversationReply(
  trackingId: string,
  message: string,
): Promise<void> {
  const response = await apiFetch(
    `/api/v1/sla-management/conversation-sla-tracking/${trackingId}/conversation/reply`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    },
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    const detail = err.detail;
    const msg =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join(' ')
          : err.message || 'Failed to send message';
    throw new Error(msg);
  }
}
