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
