'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { clearPortalToken, readPortalToken } from '@/app/(auth)/portal/lib/portal-client';
import { clearPortalSlug, portalVerifyPath, readPortalSlug } from '@/app/(auth)/portal/lib/portal-paths';
import { Skeleton } from '@/components/ui/skeleton';
import { useAccountProfileForHeader } from '@/hooks/useAccountProfileForHeader';

/**
 * The CRM-side shell of the portal forms (PORTAL-P3-ROLE-MENU): hands the signed-in salesperson's
 * portal slug (from /users/me) to the same portal components the `/portal/c/{slug}` tree renders.
 */
export function MySlug({ children }: { children: (slug: string) => ReactNode }) {
  const { salesperson, isLoading, isError } = useAccountProfileForHeader();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [ready, setReady] = useState(false);
  const mySlug = salesperson?.portalSlug ?? null;

  useEffect(() => {
    if (isLoading) return;
    // Never stuck: not a salesperson, or the profile read failed -> the CRM home.
    if (!mySlug || isError) {
      router.replace('/');
      return;
    }
    const token = readPortalToken();
    // A token that is not this salesperson's (shared device) is dropped, as the portal slug page does.
    if (token && readPortalSlug() !== mySlug) {
      clearPortalToken();
      clearPortalSlug();
    }
    if (!token || readPortalSlug() !== mySlug) {
      const deep = /^\/my-requests\/([^/]+)\/([^/]+)$/.exec(pathname ?? '');
      router.replace(
        portalVerifyPath({
          type: searchParams?.get('type') ?? deep?.[1],
          id: deep && deep[2] !== 'new' ? deep[2] : null,
        }),
      );
      return;
    }
    setReady(true);
    // Intentional: re-checked only when the profile settles.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading, isError, mySlug]);

  if (!ready || !mySlug) return <Skeleton className="h-64 w-full" />;
  return <>{children(mySlug)}</>;
}

// Trim trailing punctuation a link can absorb, as the portal pages do.
export function sanitizeId(raw: string): string {
  return (raw || '').replace(/[^0-9a-fA-F-].*$/, '');
}
