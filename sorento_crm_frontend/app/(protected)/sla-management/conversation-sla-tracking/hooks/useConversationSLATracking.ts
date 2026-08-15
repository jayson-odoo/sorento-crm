import { useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { buildDataGridParams } from '@/lib/api-client';
import {
  useRecordNeighbours,
  type RecordNeighboursResult,
} from '@/hooks/useRecordNeighbours';
import type { ConversationSLATrackingDetail } from '../types/conversationSLATracking.types';
import {
  getConversationSLATracking,
  getConversationSLATrackingDetail,
  getSLATrackingDashboardMetrics,
  deleteConversationSLATracking,
  deleteConversationSLAEventLog,
  getConversationSLAEventLogs,
  syncAssigneeFromRespond,
  postConversationSLATestOverrides,
  getSlaTrackingConversation,
  getSlaTrackingConversationPage,
  searchSlaTrackingConversation,
  postSlaTrackingConversationReply,
  CONVERSATION_SLA_TRACKING_NEIGHBOURS_PATH,
  type ConversationSLATestOverridesBody,
  type ConversationSLATrackingListParams,
} from '../services/conversationSLATrackingService';
import type { ConversationSLAEventLogsParams } from '../services/conversationSLATrackingService';

/**
 * Prev/next neighbours of a conversation SLA tracking row within the active
 * filtered+sorted list set. Serializes the list query (search/sort/policy/assignee)
 * with `buildDataGridParams` — the same serialization the list page uses — so the
 * backend honours filters identically. `page`/`limit` are sent but ignored by the
 * neighbours endpoint; `scope` is fixed to conversation server-side.
 */
export function useConversationSLATrackingNeighbours(
  trackingId: string | null,
  listParams: ConversationSLATrackingListParams,
): RecordNeighboursResult {
  const params = buildDataGridParams(listParams, {
    policy_id: listParams.policy_id,
    assigned_to: listParams.assigned_to,
    // AC-M2: the pager must walk the same pre-filtered history set the user
    // landed on, or "next" silently leaves it.
    contact: listParams.contact,
    is_resolved:
      listParams.is_resolved === undefined ? undefined : String(listParams.is_resolved),
    resolved_by: listParams.resolved_by,
  });
  return useRecordNeighbours(
    CONVERSATION_SLA_TRACKING_NEIGHBOURS_PATH,
    trackingId,
    params,
  );
}

export function useConversationSLATracking(params: ConversationSLATrackingListParams) {
  return useQuery({
    queryKey: [
      'conversation-sla-tracking',
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
      params.policy_id,
      params.status,
      params.assigned_to,
      // AC-M2 deep-link filters: part of the key, or a "View history" landing
      // renders the previously cached unfiltered page.
      params.contact,
      params.is_resolved,
      params.resolved_by,
    ],
    queryFn: () => getConversationSLATracking(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useConversationSLATrackingDetail(id: string | null) {
  return useQuery<ConversationSLATrackingDetail>({
    queryKey: ['conversation-sla-tracking-detail', id],
    queryFn: () => {
      if (!id) throw new Error('Conversation SLA tracking ID is required');
      return getConversationSLATrackingDetail(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useConversationSLAEventLogs(trackingId: string | null, params: Omit<ConversationSLAEventLogsParams, 'tracking_id'>) {
  return useQuery({
    queryKey: ['conversation-sla-event-logs', trackingId, params.page, params.limit, params.sort, params.dir, params.event_type, params.date_from, params.date_to, params.assigned_to_id],
    queryFn: () => getConversationSLAEventLogs({ ...params, tracking_id: trackingId! }),
    enabled: !!trackingId,
    retry: 1,
  });
}

export function useSLATrackingDashboardMetrics() {
  return useQuery({
    queryKey: ['sla-tracking-dashboard-metrics'],
    queryFn: () => getSLATrackingDashboardMetrics(),
    staleTime: 1000 * 60 * 5, // 5 minutes
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useDeleteConversationSLATracking() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteConversationSLATracking,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conversation-sla-tracking'] });
      queryClient.invalidateQueries({ queryKey: ['sla-tracking-dashboard-metrics'] });
    },
  });
}

export function useDeleteConversationSLAEventLog() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteConversationSLAEventLog,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conversation-sla-tracking-detail'] });
      queryClient.invalidateQueries({ queryKey: ['conversation-sla-event-logs'] });
    },
  });
}

export function useSyncAssigneeFromRespond() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: syncAssigneeFromRespond,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['conversation-sla-tracking'] });
      queryClient.invalidateQueries({ queryKey: ['conversation-sla-tracking-detail'] });
      const message = data?.message ?? (data?.updated ? 'Assignee synced from Respond.io.' : 'Sync successful.');
      toast.success(message);
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to sync assignee from Respond.io.');
    },
  });
}

export function useConversationSLATestOverrides(trackingId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ConversationSLATestOverridesBody) =>
      postConversationSLATestOverrides(trackingId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conversation-sla-tracking'] });
      queryClient.invalidateQueries({ queryKey: ['conversation-sla-tracking-detail', trackingId] });
      toast.success('Tracking updated.');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Update failed.');
    },
  });
}

/**
 * The shared contact thread. `refetchIntervalMs` opts a surface into polling so
 * an open, idle chat shows the contact's next message without a manual refresh;
 * it is opt-in because every poll is a live Respond.io call, and the surfaces
 * that merely display the thread should not pay for one. Polling stops while
 * the tab is in the background and whenever the query is disabled.
 */
export function useSlaTrackingConversation(
  trackingId: string | null,
  options?: { limit?: number; cursor?: string; enabled?: boolean; refetchIntervalMs?: number },
) {
  return useQuery({
    queryKey: ['sla-tracking-conversation', trackingId, options?.limit, options?.cursor],
    queryFn: () =>
      getSlaTrackingConversation(trackingId!, {
        limit: options?.limit ?? 50,
        cursor: options?.cursor,
      }),
    enabled: !!trackingId && (options?.enabled !== false),
    staleTime: 30 * 1000,
    refetchInterval: options?.refetchIntervalMs ?? false,
    refetchIntervalInBackground: false,
  });
}

/**
 * The two loaders `useConversationThread` needs for scroll-back and in-thread
 * search (AC-L7 / AC-L8), memoised on the ticket id.
 *
 * A hook rather than two service imports in the component: the layering rule is
 * UI -> hook -> service, and the thread hook re-runs its effects whenever a
 * loader identity changes, so where the `useCallback` lives is behaviour, not
 * tidiness.
 */
export function useSlaTrackingThreadLoaders(trackingId: string | null) {
  const loadPage = useCallback(
    (params: { before?: string; after?: string; around?: string; limit?: number }) =>
      getSlaTrackingConversationPage(trackingId ?? '', params),
    [trackingId],
  );
  const searchMessages = useCallback(
    (query: string) => searchSlaTrackingConversation(trackingId ?? '', query),
    [trackingId],
  );
  return { loadPage, searchMessages };
}

export function useSlaTrackingConversationReply(trackingId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (message: string) => postSlaTrackingConversationReply(trackingId, message),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sla-tracking-conversation', trackingId] });
      toast.success('Message sent');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to send'),
  });
}
