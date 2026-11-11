'use client';

import { useSession } from 'next-auth/react';

/**
 * `useSession()`, read as signed out where no SessionProvider wraps the tree instead of throwing,
 * so a component renders in isolation (FormComments reads the context for the same reason). Under
 * the app shell a provider is always there and nothing changes. Its own module so the many tests
 * that mock `usePermissions` do not also have to supply it.
 */
export function useSessionOrSignedOut(): Pick<ReturnType<typeof useSession>, 'data' | 'status'> {
  try {
    return useSession();
  } catch {
    return { data: null, status: 'unauthenticated' };
  }
}
