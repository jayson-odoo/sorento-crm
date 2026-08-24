import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  extendSLATracking,
  type ExtendSLAInput,
} from '../services/conversationSLATrackingService';

/**
 * Extend the resolution deadline of an SLA tracker (assignee action).
 *
 * On success invalidates every surface that shows the row's due date so the new
 * deadline appears immediately without a manual refresh (UAC-19):
 *  - the pending-tasks widget (`my-pending-sla`, `team-pending-sla`)
 *  - the SLA tracking list / detail (`conversation-sla-tracking*`)
 *  - the in-form active-tracker query on PR / stock-inquiry / complaint details
 *    (`form-sla-trackers`)
 *  - the tracker event log (`conversation-sla-event-logs`) - the extend writes one.
 */
export function useExtendSLATracking() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: ExtendSLAInput & { id: string; reason: string }) =>
      extendSLATracking(id, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-pending-sla'] });
      queryClient.invalidateQueries({ queryKey: ['team-pending-sla'] });
      queryClient.invalidateQueries({ queryKey: ['conversation-sla-tracking'] });
      queryClient.invalidateQueries({ queryKey: ['conversation-sla-tracking-detail'] });
      queryClient.invalidateQueries({ queryKey: ['conversation-sla-event-logs'] });
      queryClient.invalidateQueries({ queryKey: ['form-sla-trackers'] });
      toast.success('Resolution deadline extended.');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to extend deadline'),
  });
}
