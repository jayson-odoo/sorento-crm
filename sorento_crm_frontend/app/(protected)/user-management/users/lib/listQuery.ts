/**
 * The users list query, in one place.
 *
 * The list and the detail page's pager MUST build the same React Query key for
 * the same page, or the pager misses the cache and refetches what the list is
 * already holding (see `hooks/useListPager.ts`). So the key, the fetch and the
 * filter normalisation live here and both sides call them.
 *
 * Filters are normalised to the exact strings the URL carries: a filter on its
 * default ("all roles", "active only") is absent, never `'all'` or `null`, so a
 * key built from list state and a key built from `parseDetailSearch` are equal.
 */

import type { QueryKey } from '@tanstack/react-query';
import { joinMulti, splitMulti } from '@/lib/list-filters/multiValue';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';
import { getUsers, type UserListResponse } from '../services/userService';

export type UsersListParams = ListPagerParams;

export type UsersListPage = UserListResponse & ListPagerPage;

/** The list's filters as the URL carries them (defaults dropped). */
export function usersListFilters({
  role,
  status,
  trashed,
}: {
  role: string | null;
  status: string | null;
  trashed: string;
}): Record<string, string> {
  const filters: Record<string, string> = {};
  // FILTER-MULTISELECT: Role and Status hold several values, comma-joined; "all" is no filter.
  const roles = joinMulti(splitMulti(role).filter((v) => v !== 'all'));
  const statuses = joinMulti(splitMulti(status).filter((v) => v !== 'all'));
  if (roles) filters.roleId = roles;
  if (statuses) filters.status = statuses;
  if (trashed && trashed !== 'exclude') filters.trashed = trashed;
  return filters;
}

export function usersListQueryKey(params: UsersListParams): QueryKey {
  return [
    'user-users',
    params.pageIndex,
    params.pageSize,
    params.sorting,
    params.searchQuery,
    params.filters,
  ];
}

export function fetchUsersListPage(
  params: UsersListParams,
): Promise<UsersListPage> {
  return getUsers(params, params.filters);
}
