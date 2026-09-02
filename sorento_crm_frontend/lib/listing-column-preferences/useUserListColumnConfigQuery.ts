'use client';

import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { getUserListColumnConfig, type UserListColumnConfigResponse } from './listColumnPreferencesService';

/**
 * The one per-user, per-listing config row (`useListingColumnPreferences` and
 * `useListingViewPreferences` each write their own slice of it), read through the
 * SAME query key and options both of those hooks already use - so a third reader
 * (`SavedViewsMenu`'s personal-default lookup, S4 AC-4.4) dedupes into the same GET
 * rather than opening a second cache entry with its own `staleTime`/`retry` (nit,
 * PR #489 review round), and stays behind the hook layer instead of calling the
 * service straight from a component.
 */
export const USER_LIST_COLUMN_CONFIG_QUERY_KEY_PREFIX = 'list-column-config';

export function useUserListColumnConfigQuery(
  listingKey?: string | null,
): UseQueryResult<UserListColumnConfigResponse> {
  const key = (listingKey || '').trim();
  return useQuery({
    queryKey: [USER_LIST_COLUMN_CONFIG_QUERY_KEY_PREFIX, key],
    queryFn: () => getUserListColumnConfig(key),
    enabled: Boolean(key),
    staleTime: Infinity,
    retry: 0,
  });
}
