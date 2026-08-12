import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  getInterventionTicket,
  getInterventionTicketThread,
  getMyInterventionTickets,
  resolveInterventionTicket,
  sendInterventionTicketMessage,
  type SendTicketMessageInput,
} from '../services/interventionTicketService';

/** The viewer's open intervention tickets (worklist rows). */
export function useMyInterventionTickets(enabled = true) {
  return useQuery({
    queryKey: ['intervention-tickets', 'mine'],
    queryFn: getMyInterventionTickets,
    enabled,
    staleTime: 30 * 1000,
  });
}

/** Drawer header + composer state for one ticket. */
export function useInterventionTicket(id: string | null) {
  return useQuery({
    queryKey: ['intervention-ticket', id],
    queryFn: () => getInterventionTicket(id as string),
    enabled: !!id,
  });
}

/**
 * The shared contact thread. Keyed by ticket id, but two tickets for the same
 * contact intentionally render the SAME messages (UAC AC-C2).
 */
export function useInterventionTicketThread(id: string | null) {
  return useQuery({
    queryKey: ['intervention-ticket-thread', id],
    queryFn: () => getInterventionTicketThread(id as string),
    enabled: !!id,
    staleTime: 15 * 1000,
  });
}

/** Ticket-stamped send. Refreshes this ticket + the thread; siblings are untouched. */
export function useSendInterventionTicketMessage(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: SendTicketMessageInput) => sendInterventionTicketMessage(id, input),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['intervention-ticket-thread', id] });
      queryClient.invalidateQueries({ queryKey: ['intervention-ticket', id] });
      queryClient.invalidateQueries({ queryKey: ['intervention-tickets', 'mine'] });
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
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => resolveInterventionTicket(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['intervention-tickets', 'mine'] });
      toast.success('Ticket resolved.');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to resolve ticket'),
  });
}
