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
import { apiFetch } from '@/lib/api';
import { buildDataGridParams } from '@/lib/api-client';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';
import type { User } from '@/app/models/user';

export type UsersListParams = ListPagerParams;

export interface UsersListPage extends ListPagerPage {
  data: User[];
  pagination: { total: number; page: number };
}

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
  if (role && role !== 'all') filters.roleId = role;
  if (status && status !== 'all') filters.status = status;
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

export async function fetchUsersListPage(
  params: UsersListParams,
): Promise<UsersListPage> {
  const search = buildDataGridParams(params, params.filters);
  const response = await apiFetch(`/api/user-management/users?${search.toString()}`);

  if (!response.ok) {
    throw new Error(
      'Oops! Something didn’t go as planned. Please try again in a moment.',
    );
  }

  const json = await response.json();
  if (json.data?.length) {
    json.data = json.data.map((u: Record<string, unknown>) => ({
      ...u,
      isTrashed: u.is_trashed ?? u.isTrashed,
      dailySlaSummarySubscribed:
        u.daily_sla_summary_subscribed ?? u.dailySlaSummarySubscribed ?? true,
    }));
  }
  return json as UsersListPage;
}
