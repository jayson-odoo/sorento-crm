/**
 * The contacts list query, in one place.
 *
 * The list and the detail shell's pager MUST build the same React Query key for
 * the same page, or the pager misses the cache (see `hooks/useListPager.ts`).
 * Before S3 the detail shell fetched its own 100 newest contacts instead, so the
 * chevrons walked a set that had nothing to do with the list the user left.
 */

import type { QueryKey } from '@tanstack/react-query';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';
import {
  getContacts,
  type RespondContactListResponse,
} from '../[id]/services/contactService';

export type ContactsListParams = ListPagerParams;

/**
 * The list's filters as the URL carries them (contract mirrors `usersListFilters`
 * in `../../users/lib/listQuery.ts`) - a filter on its default (no level filter at
 * all) is absent, never an empty string, so a key built from list state and a key
 * built from `parseDetailSearch` are equal.
 *
 * `chatbot_memory_level=own` (Settings > Chatbot > Memory's "N contacts" link,
 * AC-MEM028) is the only value this lane sends - the backend filters to
 * `chatbot_memory_level IS NOT NULL`.
 */
export function contactsListFilters({
  chatbotMemoryLevel,
  customersNone = false,
}: {
  chatbotMemoryLevel: string | null;
  customersNone?: boolean;
}): Record<string, string> {
  const filters: Record<string, string> = {};
  if (chatbotMemoryLevel) filters.chatbot_memory_level = chatbotMemoryLevel;
  // `customers=none`: the contacts with no linked customer (bulk Link customers worklist).
  if (customersNone) filters.customers = 'none';
  return filters;
}

export function contactsListQueryKey(params: ContactsListParams): QueryKey {
  return [
    'respond-contacts',
    params.pageIndex,
    params.pageSize,
    params.sorting,
    params.searchQuery,
    params.filters,
  ];
}

export function fetchContactsPage(
  params: ContactsListParams,
): Promise<RespondContactListResponse> {
  return getContacts(
    {
      pageIndex: params.pageIndex,
      pageSize: params.pageSize,
      // The list GET wants a sort even when the grid has none, and `created_at`
      // desc is what the screen opens on.
      sorting: params.sorting.length ? params.sorting : [{ id: 'created_at', desc: true }],
      searchQuery: params.searchQuery,
    },
    params.filters,
  );
}

/** The pager's two hooks into the contacts list. */
export const contactsPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey => contactsListQueryKey(params),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> => fetchContactsPage(params),
};
