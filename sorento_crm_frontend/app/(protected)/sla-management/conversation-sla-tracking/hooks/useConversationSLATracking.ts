import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import type { ConversationSLATrackingDetail } from '../types/conversationSLATracking.types';
import { getConversationSLATracking, getConversationSLATrackingDetail, getSLATrackingDashboardMetrics, deleteConversationSLATracking, deleteConversationSLAEventLog, getConversationSLAEventLogs, syncAssigneeFromRespond, postConversationSLATestOverrides, type ConversationSLATestOverridesBody } from '../services/conversationSLATrackingService';
import type { ConversationSLAEventLogsParams } from '../services/conversationSLATrackingService';

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
