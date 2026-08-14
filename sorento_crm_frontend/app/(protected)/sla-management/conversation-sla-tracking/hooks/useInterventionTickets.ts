import { useMutation, useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  getInterventionTicket,
  resolveInterventionTicket,
  sendInterventionTicketMessage,
  type SendTicketMessageInput,
} from '../services/interventionTicketService';

/**
 * The viewer's open intervention tickets are worklist rows already covered by
 * `getMyPendingSLA` (`/my-pending`, flagged `is_intervention_ticket: true`) -
 * there is no separate ticket-listing endpoint. This module covers only what's
 * specific to a ticket once it's opened: detail, thread, send, resolve.
 */

/** Drawer header + composer state for one ticket. */
export function useInterventionTicket(id: string | null) {
  return useQuery({
    queryKey: ['intervention-ticket', id],
    queryFn: () => getInterventionTicket(id as string),
    enabled: !!id,
  });
}

/**
 * The shared contact thread has NO hook here: it is the same
 * GET /{id}/conversation the SLA detail page reads, so the drawer uses
 * `useSlaTrackingConversation` (./useConversationSLATracking) and both surfaces
 * share the ONE key `['sla-tracking-conversation', id, ...]`. Two tickets for
 * the same contact still render the SAME messages (UAC AC-C2).
 */

/** Ticket-stamped send. The caller refreshes; siblings are untouched. */
export function useSendInterventionTicketMessage(id: string) {
  return useMutation({
    mutationFn: (input: SendTicketMessageInput) => sendInterventionTicketMessage(id, input),
    onSuccess: (result, input) => {
      // NO invalidateQueries here. The drawer's `onSent` already refetches the
      // ticket AND the thread explicitly (InterventionTicketDrawer), so
      // invalidating the same two keys fired every GET twice per send - two
      // round trips to Respond.io for one reply. One trigger, and it is the
      // caller's, because the caller also owns the follow-up pulses that chase
      // the delivery ticks.
      // The worklist is NOT a react-query cache entry: MyPendingSLAWidget calls
      // getMyPendingSLA into component state, so there is no key to invalidate.
      // The drawer's onSent reloads it (InterventionTicketDrawer -> onSent).
      // A partially-delivered multi-file send returns 200: the composer names
      // the file that did not make it and keeps it staged, so a blanket
      // "Message sent" here would contradict it.
      if (result.attachments?.failed) return;
      // Files went up but none came back delivered: the composer says so and
      // keeps them staged. A "Message sent" toast beside that error is a lie.
      if ((input.attachments?.length ?? 0) > 0 && !(result.attachments?.delivered?.length ?? 0)) {
        return;
      }
      toast.success(
        result.sent_as === 'template' ? 'Delivered as a template message' : 'Message sent',
      );
    },
    // No onError toast: the composer owns send failures (it keeps the draft and
    // renders the typed no-template case), and two toasts for one failure is noise.
  });
}

/** Resolve one ticket. Sibling tickets for the same contact stay open. */
export function useResolveInterventionTicket() {
  return useMutation({
    mutationFn: (id: string) => resolveInterventionTicket(id),
    // The worklist reload is the drawer's onResolved (see the send hook above):
    // that list lives in component state, not in the query cache.
    onSuccess: () => {
      toast.success('Ticket resolved.');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to resolve ticket'),
  });
}
