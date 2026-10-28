'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import {
  PortalUnauthorizedError,
  clearPortalToken,
  fetchMe,
  readPortalToken,
} from '@/app/(auth)/portal/lib/portal-client';
import { clearPortalSlug, readPortalSlug } from '@/app/(auth)/portal/lib/portal-paths';
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
    let cancelled = false;
    const toVerify = () => {
      const deep = /^\/my-requests\/([^/]+)\/([^/]+)$/.exec(pathname ?? '');
      const qs = new URLSearchParams();
      const type = searchParams?.get('type') ?? deep?.[1];
      if (type) qs.set('type', type);
      if (deep && deep[2] !== 'new') qs.set('id', deep[2]);
      const q = qs.toString();
      router.replace(`/my-requests/verify${q ? `?${q}` : ''}`);
    };
    const dropToken = () => {
      clearPortalToken();
      clearPortalSlug();
    };
    const token = readPortalToken();
    // A token that is not this salesperson's (shared device) is dropped, as the portal slug page does.
    if (!token || readPortalSlug() !== mySlug) {
      if (token) dropToken();
      toVerify();
      return;
    }
    // The stored slug is only a hint: the token's own identity must be this salesperson's too.
    void fetchMe()
      .then((me) => {
        if (cancelled) return;
        if (me.portal_slug !== mySlug) {
          dropToken();
          toVerify();
          return;
        }
        setReady(true);
      })
      .catch((e) => {
        if (cancelled) return;
        if (e instanceof PortalUnauthorizedError) {
          toVerify();
          return;
        }
        // Not an identity answer (network): the page shows its own error.
        setReady(true);
      });
    return () => {
      cancelled = true;
    };
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
