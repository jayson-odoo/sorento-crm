import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  createTicketComment,
  getTicketComments,
  type CreateTicketCommentInput,
} from '../services/ticketCommentService';

/** Query key for one ticket's internal notes (UAC AC-L1). */
export const ticketCommentsKey = (id: string | null) => ['ticket-comments', id] as const;

/** The internal notes on a ticket, oldest first. Disabled with no ticket id. */
export function useTicketComments(id: string | null) {
  return useQuery({
    queryKey: ticketCommentsKey(id),
    queryFn: () => getTicketComments(id as string),
    enabled: !!id,
  });
}

/**
 * Add an internal note. Unlike the reply send, this one DOES invalidate its own
 * key: the note list has no independent refetch trigger (the thread poll only
 * covers messages), so the composer's caller has nothing else to lean on.
 */
export function useCreateTicketComment(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateTicketCommentInput) => createTicketComment(id, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ticketCommentsKey(id) });
      toast.success('Note added');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to add the note'),
  });
}
