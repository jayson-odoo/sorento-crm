'use client';

import { useQuery } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { apiFetch } from '@/lib/api';
import { resolveUserAvatarSrc } from '@/lib/helpers';

/**
 * Same source as User Management → Account layout: GET /api/user-management/account/
 * (includes CloudFront-signed avatar). JWT session alone often has an unsigned URL that 403s in <img>.
 */
export function useAccountProfileForHeader() {
  const { data: session, status } = useSession();

  const { data: profile } = useQuery({
    queryKey: ['account-profile'],
    queryFn: async () => {
      const response = await apiFetch('/api/user-management/account/');
      if (!response.ok) {
        return null;
      }
      return response.json() as Promise<{
        avatar?: string | null;
        name?: string | null;
        email?: string | null;
      }>;
    },
    enabled: status === 'authenticated',
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: 1,
  });

  const avatarSrc = resolveUserAvatarSrc(
    profile?.avatar ?? session?.user?.avatar,
  );

  return {
    avatarSrc,
    displayName: profile?.name ?? session?.user?.name ?? '',
    displayEmail: profile?.email ?? session?.user?.email ?? '',
  };
}
