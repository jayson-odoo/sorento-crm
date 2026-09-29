import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';

import {
  getContactCustomers,
  linkContactCustomers,
} from '../services/contactCustomersService';

export const contactCustomersKey = (contactId: string) => ['contact-customers', contactId];

export function useContactCustomers(contactId: string) {
  return useQuery({
    queryKey: contactCustomersKey(contactId),
    queryFn: () => getContactCustomers(contactId),
    enabled: !!contactId,
    retry: 1,
  });
}

export function useLinkContactCustomers(contactId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (customerIds: string[]) => linkContactCustomers(contactId, customerIds),
    onSuccess: (links) => {
      queryClient.invalidateQueries({ queryKey: contactCustomersKey(contactId) });
      queryClient.invalidateQueries({ queryKey: ['customer-linked-contacts'] });
      toast.success(links.length === 1 ? 'Customer linked' : `${links.length} customers linked`);
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to link customers'),
  });
}
