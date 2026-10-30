'use client';

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { fetchMyPermissions } from '@/lib/permissions-service';

const PERMISSIONS_QUERY_KEY = ['my-permissions'];
const NO_PERMISSIONS: string[] = [];

/**
 * `useSession()`, read as signed out where no SessionProvider wraps the tree instead of throwing,
 * so a component that only branches on a slug renders in isolation (FormComments reads the context
 * for the same reason). Under the app shell a provider is always there and nothing changes.
 */
function useSessionOrSignedOut(): Pick<ReturnType<typeof useSession>, 'data' | 'status'> {
  try {
    return useSession();
  } catch {
    return { data: null, status: 'unauthenticated' };
  }
}

export function usePermissions() {
  const { status } = useSessionOrSignedOut();
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: PERMISSIONS_QUERY_KEY,
    queryFn: fetchMyPermissions,
    enabled: status === 'authenticated',
    staleTime: 5 * 60 * 1000,
    // Its failure is reported in place (RequireAccess + the shell banner), not as a toast.
    meta: { silent: true },
  });
  // Stable identities: consumers put these in effect deps (SearchDialog does, and
  // sets state there). A fresh [] / Set per render while the load has failed
  // re-ran that effect forever and froze the page (NEVER-STUCK-UI, lever L6).
  const permissions = data ?? NO_PERMISSIONS;
  const set = useMemo(() => new Set(permissions), [permissions]);
  // "We could not find out" (NEVER-STUCK-UI S3, lever L6), which is not "denied":
  // an empty set from a failed read must never render as "no access". A refetch
  // that fails over a set already loaded keeps that set, so it is not an error.
  const isError = !!error && data === undefined;
  return { permissions, permissionSet: set, isLoading, isError, isFetching, error, refetch };
}

export function useHasPermission(slug: string): boolean {
  const { permissionSet, isLoading } = usePermissions();
  const { data: session, status } = useSessionOrSignedOut();
  if (status !== 'authenticated' || !session || isLoading) return false;
  if (!slug) return true;
  return permissionSet.has(slug);
}

export function useHasAnyPermission(slugs: string[]): boolean {
  const { permissionSet, isLoading } = usePermissions();
  const { data: session, status } = useSessionOrSignedOut();
  if (status !== 'authenticated' || !session || isLoading) return false;
  if (!slugs.length) return true;
  return slugs.some((s) => permissionSet.has(s));
}

export { PERMISSIONS_QUERY_KEY };
