import { useQuery } from '@tanstack/react-query';

import { getContact } from '../services/contactService';

export const contactKey = (contactId: string) => ['respond-contact', contactId];

export function useContactQuery(contactId: string) {
  return useQuery({
    queryKey: contactKey(contactId),
    queryFn: () => getContact(contactId),
    enabled: !!contactId,
  });
}
