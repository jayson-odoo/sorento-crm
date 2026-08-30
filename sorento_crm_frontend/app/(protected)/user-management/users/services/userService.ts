/**
 * ============================================================================
 * Users - feature service
 * ============================================================================
 * Layering: UI (user-list, user-hero) -> lib/listQuery (the shared key + fetch)
 * -> THIS service -> lib/api -> backend. No component and no query builder
 * talks to `apiFetch` on its own, and the failure message comes off the
 * response rather than being invented here.
 *
 *   GET /api/v1/user-management/users?page&limit&sort&dir&query&roleId&status&trashed
 *     200 -> { data: User[], pagination: { total, page } }
 */

import { apiFetch } from '@/lib/api';
import {
  buildDataGridParams,
  extractApiError,
  type DataGridParamsInput,
} from '@/lib/api-client';
import type { User } from '@/app/models/user';

export interface UserListResponse {
  data: User[];
  pagination: { total: number; page: number };
}

/**
 * One page of the users list.
 *
 * The backend still answers in snake_case for two fields the UI reads in camel,
 * so they are normalised here rather than at each reader: a missing
 * `daily_sla_summary_subscribed` means subscribed, which is the server default.
 */
export async function getUsers(
  params: DataGridParamsInput,
  filters: Record<string, string> = {},
): Promise<UserListResponse> {
  const query = buildDataGridParams(params, filters);
  const response = await apiFetch(`/api/user-management/users?${query.toString()}`);

  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load users'));
  }

  const page = (await response.json()) as UserListResponse;
  return {
    ...page,
    data: (page.data ?? []).map((row) => {
      const raw = row as User & {
        is_trashed?: boolean;
        daily_sla_summary_subscribed?: boolean;
      };
      return {
        ...row,
        isTrashed: raw.is_trashed ?? row.isTrashed,
        dailySlaSummarySubscribed:
          raw.daily_sla_summary_subscribed ?? row.dailySlaSummarySubscribed ?? true,
      };
    }),
  };
}

/**
 * Trash a user (the backend's DELETE is the soft one - the account is restorable
 * from the list's "Trashed only" filter).
 *
 * Called by the deferred `user.delete` action once its window lapses; nothing
 * else deletes a user, so the confirmation the dialog used to demand is now the
 * ten seconds the reader has to change their mind.
 */
export async function deleteUser(id: string): Promise<void> {
  const response = await apiFetch(`/api/user-management/users/${id}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to trash the user'));
  }
}
