import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  getTeamPendingSLA,
  getVisibleUsers,
  takeoverSLATracking,
  reassignSLATracking,
  cancelTakeover,
  rejectTakeover,
  type TeamPendingFilters,
} from '../services/conversationSLATrackingService';

/** Visible-team pending tasks (Team Tasks page + home widget "My Team" mode). */
export function useTeamPendingSLA(filters: TeamPendingFilters) {
  return useQuery({
    queryKey: ['team-pending-sla', filters.page, filters.limit, filters.assignee, filters.team, filters.query],
    queryFn: () => getTeamPendingSLA(filters),
    retry: 1,
  });
}

/** Scope-B users for the Reassign / Coverage pickers. */
export function useVisibleUsers(enabled = true) {
  return useQuery({
    queryKey: ['sla-visible-users'],
    queryFn: () => getVisibleUsers(),
    staleTime: 1000 * 60 * 5,
    enabled,
  });
}

function invalidatePendingQueries(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ['team-pending-sla'] });
  queryClient.invalidateQueries({ queryKey: ['my-pending-sla'] });
  queryClient.invalidateQueries({ queryKey: ['conversation-sla-tracking'] });
}

export function useTakeoverSLATracking() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, teamId }: { id: string; teamId: string }) =>
      takeoverSLATracking(id, teamId),
    onSuccess: (result) => {
      invalidatePendingQueries(queryClient);
      if (result.committed) {
        toast.success('Task taken over - it now appears in My Pending.');
      } else if (result.already_pending) {
        toast.info('A takeover is already pending for this task.');
      } else {
        toast.success('Takeover started - the assignee can reject during the cooldown.');
      }
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to take over task'),
  });
}

export function useCancelTakeover() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (requestId: string) => cancelTakeover(requestId),
    onSuccess: () => {
      invalidatePendingQueries(queryClient);
      toast.success('Takeover cancelled.');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to cancel takeover'),
  });
}

export function useRejectTakeover() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (requestId: string) => rejectTakeover(requestId),
    onSuccess: () => {
      invalidatePendingQueries(queryClient);
      toast.success('Takeover rejected - the task stays with you.');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to reject takeover'),
  });
}

export function useReassignSLATracking() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, userId }: { id: string; userId: string }) =>
      reassignSLATracking(id, userId),
    onSuccess: () => {
      invalidatePendingQueries(queryClient);
      toast.success('Task reassigned.');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to reassign task'),
  });
}
