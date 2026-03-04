'use client';

import { useQuery } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { fetchMyPermissions } from '@/lib/permissions-service';

const PERMISSIONS_QUERY_KEY = ['my-permissions'];

export function usePermissions() {
  const { status } = useSession();
  const { data: permissions = [], isLoading, error, refetch } = useQuery({
    queryKey: PERMISSIONS_QUERY_KEY,
    queryFn: fetchMyPermissions,
    enabled: status === 'authenticated',
    staleTime: 5 * 60 * 1000,
  });
  const set = new Set(permissions);
  return { permissions, permissionSet: set, isLoading, error, refetch };
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
