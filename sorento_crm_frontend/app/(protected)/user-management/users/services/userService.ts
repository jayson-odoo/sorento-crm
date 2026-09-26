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
  codedError,
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

/**
 * The row switch on the users list: is this user sent the daily conversation
 * summary? PATCHed one user at a time, so the write is the whole story and the
 * caller's optimistic patch (S7-01) is what the reader sees move.
 */
export async function setDailySlaSummarySubscription(
  id: string,
  subscribed: boolean,
): Promise<void> {
  const response = await apiFetch(
    `/api/user-management/users/${id}/daily-sla-summary-subscription`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subscribed }),
    },
  );

  if (!response.ok) {
    throw new Error(
      await extractApiError(response, 'Failed to update the conversation summary setting'),
    );
  }
}

export interface UserSelectOption {
  id: string;
  name: string | null;
  email: string | null;
}

export interface CreateUserInput {
  name: string;
  email?: string | null;
  contact_number?: string | null;
  respond_contact_id?: string | null;
  role_ids: string[];
  superior_id?: string | null;
  company_ids: string[];
}

/**
 * Create a user (S3, AC-41 / AC-58): no invitation checkbox, no `/invite`
 * branch - this is the only way the Add user modal saves. `codedError` so the
 * dialog can branch on `CONTACT_ALREADY_LINKED` / `PHONE_BELONGS_TO_USER` /
 * `EMAIL_TAKEN` instead of just showing the message.
 */
export async function createUser(input: CreateUserInput): Promise<User> {
  const response = await apiFetch('/api/user-management/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw await codedError(response, 'Failed to add user');
  }
  return (await response.json()) as User;
}

/** Link or unlink a user's WhatsApp contact (S3 1.3): `null` unlinks. */
export async function updateUserContactLink(
  userId: string,
  respondContactId: string | null,
): Promise<User> {
  const response = await apiFetch(`/api/user-management/users/${userId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ respond_contact_id: respondContactId }),
  });
  if (!response.ok) {
    throw await codedError(response, 'Failed to update the linked contact');
  }
  return (await response.json()) as User;
}

/** "Use new number" (AC-46 / AC-54): takes the linked contact's own phone. */
export async function useNewNumber(userId: string, phoneNumber: string): Promise<User> {
  const response = await apiFetch(`/api/user-management/users/${userId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ contact_number: phoneNumber }),
  });
  if (!response.ok) {
    throw await codedError(response, 'Failed to update the phone number');
  }
  return (await response.json()) as User;
}

/**
 * Resolve the user already holding a phone number, for "Link this contact to
 * <name> instead" / "Open user" (AC-42). Null when it cannot be resolved -
 * the caller falls back to the plain error message, which already names them.
 */
export async function findUserByPhone(phone: string): Promise<UserSelectOption | null> {
  const params = new URLSearchParams({ phone });
  const response = await apiFetch(`/api/user-management/users/select?${params.toString()}`);
  if (!response.ok) return null;
  const rows = (await response.json()) as UserSelectOption[];
  return rows[0] ?? null;
}

/** Resolve the user already holding a WhatsApp contact ("Open user", AC-43). */
export async function findUserByContact(
  respondContactId: string,
): Promise<UserSelectOption | null> {
  const params = new URLSearchParams({ respond_contact_id: respondContactId });
  const response = await apiFetch(`/api/user-management/users/select?${params.toString()}`);
  if (!response.ok) return null;
  const rows = (await response.json()) as UserSelectOption[];
  return rows[0] ?? null;
}

/**
 * Users with no linked contact, for "Link existing user" on a contact's User
 * account section (S3 1.7's `unlinked=true` filter).
 */
export async function listUnlinkedUsers(query?: string): Promise<UserSelectOption[]> {
  const params = new URLSearchParams({ status: 'ACTIVE', unlinked: 'true' });
  if (query?.trim()) params.set('query', query.trim());
  const response = await apiFetch(`/api/user-management/users/select?${params.toString()}`);
  if (!response.ok) return [];
  return (await response.json()) as UserSelectOption[];
}
