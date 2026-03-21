import { useQuery } from '@tanstack/react-query';
import { getContactAccessTypes } from '../services/contactAccessTypeService';

export function useContactAccessTypes() {
  return useQuery({
    queryKey: ['contact-access-types'],
    queryFn: getContactAccessTypes,
    staleTime: 5 * 60 * 1000,
  });
}
