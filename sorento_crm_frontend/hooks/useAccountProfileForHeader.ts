'use client';

import { useQuery } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { apiFetch } from '@/lib/api';
import { resolveUserAvatarSrc } from '@/lib/helpers';
import { useImpersonationSession } from '@/lib/impersonation-store';

/**
 * Same source as User Management → Account layout: GET /api/user-management/account/
 * (includes CloudFront-signed avatar). JWT session alone often has an unsigned URL that 403s in <img>.
 */
export function useAccountProfileForHeader() {
  const { data: session, status } = useSession();
  // Under CRM impersonation the profile (and its salesperson block) is the TARGET's: only an
  // `/api/v1/` URL carries the X-Impersonate-User-Id header, the account BFF route does not.
  const targetId = useImpersonationSession()?.targetUser.id ?? null;

  const queryKey = targetId ? ['account-profile', targetId] : ['account-profile'];
  const { data: profile, isError } = useQuery({
    queryKey,
    queryFn: async () => {
      const response = await apiFetch(
        targetId ? '/api/v1/user-management/users/me' : '/api/user-management/account/',
      );
      if (!response.ok) {
        return null;
      }
      return response.json() as Promise<{
        avatar?: string | null;
        name?: string | null;
        email?: string | null;
        salesperson?: {
          portal_kinds: string[];
          portal_slug: string;
          contact_id?: string | null;
          contact_name?: string | null;
        } | null;
        /** UI v2 (phase 0): the effective version, whether v2 is offered, and the user's mode. */
        ui_version?: 'v1' | 'v2';
        ui_version_stored?: 'v1' | 'v2';
        ui_v2_available?: boolean;
        theme_mode?: 'light' | 'dark' | 'system';
      }>;
    },
    enabled: status === 'authenticated',
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnReconnect: false,
    retry: 1,
  });

  const avatarSrc = resolveUserAvatarSrc(
    profile?.avatar ?? session?.user?.avatar,
  );

  const salesperson = profile?.salesperson
    ? { portalKinds: profile.salesperson.portal_kinds, portalSlug: profile.salesperson.portal_slug,
        contactId: profile.salesperson.contact_id ?? null,
        // Left out when absent (the shape the existing callers and tests read is unchanged).
        contactName: profile.salesperson.contact_name ?? undefined,
      }
    : null;

  return {
    profile,
    queryKey,
    salesperson,
    // Settled = answered, failed, or answered null; a disabled query (session still loading) is not.
    isLoading: status === 'loading' || (status === 'authenticated' && profile === undefined && !isError),
    isError,
    avatarSrc,
    displayName: profile?.name ?? session?.user?.name ?? '',
    displayEmail: profile?.email ?? session?.user?.email ?? '',
  };
}
