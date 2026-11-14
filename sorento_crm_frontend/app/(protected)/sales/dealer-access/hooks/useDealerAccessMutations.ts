import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  DealerAccessGrantError,
  grant,
  retryRespond,
  updatePerson,
  type DealerAccessGrantBody,
  type DealerAccessUpdateBody,
} from '@/services/dealerAccessService';
import { DEALER_ACCESS_KEY } from './useDealerAccessQuery';

/** Add people. A refusal that names rows is shown under those rows, so it is not also toasted. */
export function useDealerAccessGrant() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: DealerAccessGrantBody) => grant(body),
    onSuccess: (_result, body) => {
      queryClient.invalidateQueries({ queryKey: DEALER_ACCESS_KEY });
      toast.success(body.people.length === 1 ? 'Access given' : 'Access given to everyone');
    },
    onError: (error: Error) => {
      if (error instanceof DealerAccessGrantError && Object.keys(error.rowErrors).length > 0) return;
      toast.error(error.message || 'Failed to give access');
    },
  });
}

/** Edit one person's accounts and access. The dialog shows the refusal under its form. */
export function useDealerAccessUpdate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ contactId, ...body }: DealerAccessUpdateBody & { contactId: string }) =>
      updatePerson(contactId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: DEALER_ACCESS_KEY });
      toast.success('Access updated');
    },
  });
}

/** "Try again in Respond.io" (N5.5). A Respond.io failure is an answer the caller shows, not a toast. */
export function useDealerAccessRespondRetry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (contactId: string) => retryRespond(contactId),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: DEALER_ACCESS_KEY });
      if (result.respond === 'ok') toast.success('Now in Respond.io');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to reach Respond.io');
    },
  });
}
