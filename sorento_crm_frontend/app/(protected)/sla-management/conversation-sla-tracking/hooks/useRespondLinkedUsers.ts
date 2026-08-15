'use client';

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { getUsersSelect, type UserSelectItem } from '@/services/userSelectService';

/**
 * Which colleagues carry a Respond.io identity (UAC AC-N7).
 *
 * A reply sent by a user with no Respond mapping cannot carry a real sender
 * identity in the contact's inbox, so the reassign picker says who is linked
 * and can filter to them.
 *
 * BEST EFFORT ON PURPOSE. The scope-B picker source
 * (`.../conversation-sla-tracking/visible-users`) does not carry the linkage,
 * so it is read from the shared user-select endpoint, which is gated by
 * `user_management.users.view` - a permission an SLA agent may well not hold.
 * A 403 there must not break reassignment, so a failure degrades to "linkage
 * unknown": no badges, no filter toggle, the picker works exactly as before.
 * (Backend follow-up: have `visible-users` return `respond_user_id` and this
 * whole second call disappears.)
 */
export function isRespondLinkedUser(user: Pick<UserSelectItem, 'respond_user_id'>): boolean {
  return String(user.respond_user_id ?? '').trim() !== '';
}

export interface RespondLinkedUsers {
  /** Ids of the Respond-linked users. Empty while unknown. */
  linkedIds: Set<string>;
  /** False when the linkage could not be read - hide the badge and the filter. */
  isKnown: boolean;
  isLoading: boolean;
}

export function useRespondLinkedUserIds(enabled = true): RespondLinkedUsers {
  const { data, isError, isLoading } = useQuery({
    queryKey: ['respond-linked-users'],
    queryFn: () => getUsersSelect({ status: 'ACTIVE' }),
    enabled,
    staleTime: 5 * 60 * 1000,
    // One 403 is the answer, not a transient failure worth three round trips.
    retry: false,
  });

  const linkedIds = useMemo(
    () => new Set((data ?? []).filter(isRespondLinkedUser).map((u) => u.id)),
    [data],
  );

  return { linkedIds, isKnown: !isError && Array.isArray(data), isLoading };
}
