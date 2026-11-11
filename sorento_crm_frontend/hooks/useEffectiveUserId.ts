'use client';

import { useSession } from 'next-auth/react';
import { useImpersonationSession } from '@/lib/impersonation-store';

/**
 * The acting user's id, impersonation-aware.
 *
 * Impersonation swaps the BACKEND principal via the `X-Impersonate-User-Id` header
 * (see lib/api.ts) but does NOT change the NextAuth session - so `session.user.id`
 * stays the admin's id while impersonating. Any "is this me?" UI gate (e.g. assignee
 * checks) must use THIS value, not `session.user.id`, or it will be wrong for the
 * whole impersonation session.
 *
 * Returns the impersonated target's id when impersonating, otherwise the logged-in
 * user's id (or null when unauthenticated).
 */
export function useEffectiveUserId(): string | null {
  const { data: session } = useSession();
  const impersonation = useImpersonationSession();
  return impersonation?.targetUser?.id ?? session?.user?.id ?? null;
}

/**
 * The acting user's name, impersonation-aware like `useEffectiveUserId`: the impersonated
 * target's name during a view-as (the backend saves created_by as that user), otherwise the
 * signed-in user's. A new quotation shows it as Prepared By (owner ruling 11 Nov 2026).
 */
export function useEffectiveUserName(): string | null {
  // Read as signed out where no SessionProvider wraps the tree (the quotation form renders in
  // isolation in its tests), the same guard as `usePermissions`.
  let session: ReturnType<typeof useSession>['data'] = null;
  try {
    session = useSession().data;
  } catch {
    session = null;
  }
  const impersonation = useImpersonationSession();
  if (impersonation?.targetUser) {
    return impersonation.targetUser.name || impersonation.targetUser.email || null;
  }
  return session?.user?.name ?? null;
}
