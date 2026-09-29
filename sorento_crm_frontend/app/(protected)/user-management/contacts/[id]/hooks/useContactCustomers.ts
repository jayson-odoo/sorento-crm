import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';

import {
  getContactCustomers,
  linkContactCustomer,
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

export function useLinkContactCustomer(contactId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ customerId }: { customerId: string }) =>
      linkContactCustomer(contactId, customerId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: contactCustomersKey(contactId) });
      toast.success('Customer linked');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to link customer'),
  });
}
