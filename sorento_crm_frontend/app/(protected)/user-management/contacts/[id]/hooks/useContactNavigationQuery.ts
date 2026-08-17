import { useQuery } from '@tanstack/react-query';
import type { DataGridParamsInput } from '@/lib/api-client';

import { getContacts } from '../services/contactService';

/**
 * One page of contacts, newest first, purely to feed prev/next record navigation
 * on the detail shell. Cached for the session so stepping through records does
 * not refetch the list on every hop.
 */
const NAVIGATION_PARAMS: DataGridParamsInput = {
  pageIndex: 0,
  pageSize: 100,
  sorting: [{ id: 'created_at', desc: true }],
  searchQuery: '',
};

export const contactNavigationKey = () => ['respond-contacts-nav', NAVIGATION_PARAMS];

export function useContactNavigationQuery() {
  return useQuery({
    queryKey: contactNavigationKey(),
    queryFn: () => getContacts(NAVIGATION_PARAMS),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: 1,
  });
}
