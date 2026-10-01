'use client';

import { useQuery } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { fetchMyPermissions } from '@/lib/permissions-service';

const PERMISSIONS_QUERY_KEY = ['my-permissions'];

export function usePermissions() {
  const { status } = useSession();
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: PERMISSIONS_QUERY_KEY,
    queryFn: fetchMyPermissions,
    enabled: status === 'authenticated',
    staleTime: 5 * 60 * 1000,
  });
  const permissions = data ?? [];
  const set = new Set(permissions);
  // "We could not find out" (NEVER-STUCK-UI S3, lever L6), which is not "denied":
  // an empty set from a failed read must never render as "no access". A refetch
  // that fails over a set already loaded keeps that set, so it is not an error.
  const isError = !!error && data === undefined;
  return { permissions, permissionSet: set, isLoading, isError, isFetching, error, refetch };
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
