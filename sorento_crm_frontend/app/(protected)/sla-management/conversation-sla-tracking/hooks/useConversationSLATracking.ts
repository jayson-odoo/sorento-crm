import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
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
  });
  return useRecordNeighbours(
    CONVERSATION_SLA_TRACKING_NEIGHBOURS_PATH,
    trackingId,
    params,
  );
}

export function useConversationSLATracking(params: DataGridApiFetchParams & { policy_id?: string; status?: string; assigned_to?: string }) {
  return useQuery({
    queryKey: ['conversation-sla-tracking', params.pageIndex, params.pageSize, params.sorting, params.searchQuery, params.policy_id, params.status, params.assigned_to],
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

export function useSlaTrackingConversation(
  trackingId: string | null,
  options?: { limit?: number; cursor?: string; enabled?: boolean },
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
  });
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
