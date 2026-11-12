import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  DealerAccessGrantError,
  grant,
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
