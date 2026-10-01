'use client';

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { fetchMyPermissions } from '@/lib/permissions-service';

const PERMISSIONS_QUERY_KEY = ['my-permissions'];

/**
 * One shared empty list. A `= []` default made a new array on every render while the
 * permissions were missing (loading, or failed because the session died), and an effect
 * depending on it (the universal search dialog) re-ran forever; after a click the loop
 * never yielded and froze the page (SESSION-NEVER-STUCK).
 */
const NO_PERMISSIONS: string[] = [];

export function usePermissions() {
  const { status } = useSession();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: PERMISSIONS_QUERY_KEY,
    queryFn: fetchMyPermissions,
    enabled: status === 'authenticated',
    staleTime: 5 * 60 * 1000,
  });
  const permissions = data ?? NO_PERMISSIONS;
  const permissionSet = useMemo(() => new Set(permissions), [permissions]);
  return { permissions, permissionSet, isLoading, error, refetch };
}

export function useHasPermission(slug: string): boolean {
  const { permissionSet, isLoading } = usePermissions();
  const { data: session, status } = useSession();
  if (status !== 'authenticated' || !session || isLoading) return false;
  if (!slug) return true;
  return permissionSet.has(slug);
}

export function useHasAnyPermission(slugs: string[]): boolean {
  const { permissionSet, isLoading } = usePermissions();
  const { data: session, status } = useSession();
  if (status !== 'authenticated' || !session || isLoading) return false;
  if (!slugs.length) return true;
  return slugs.some((s) => permissionSet.has(s));
}

export { PERMISSIONS_QUERY_KEY };
