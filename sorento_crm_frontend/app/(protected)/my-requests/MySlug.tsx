'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import {
  PortalUnauthorizedError,
  clearImpersonationToken,
  clearPortalToken,
  fetchMeWithGrace,
  isImpersonationToken,
  readPortalToken,
  writePortalToken,
} from '@/app/(auth)/portal/lib/portal-client';
import {
  clearPortalSlug,
  readPortalSlug,
} from '@/app/(auth)/portal/lib/portal-paths';
import { Skeleton } from '@/components/ui/skeleton';
import { useAccountProfileForHeader } from '@/hooks/useAccountProfileForHeader';
import { useImpersonationSession } from '@/lib/impersonation-store';
import {
  fetchImpersonatedUserContactId,
  startContactImpersonation,
} from '@/services/contactImpersonationService';

let contactViewStart: Promise<string> | null = null;

/** One contact impersonation start per visit: a StrictMode double effect shares this promise. */
function startContactViewOnce(): Promise<string> {
  if (!contactViewStart) {
    contactViewStart = (async () => {
      const contactId = await fetchImpersonatedUserContactId();
      if (!contactId) throw new Error('no linked contact');
      const started = await startContactImpersonation(contactId);
      const token = new URL(
        started.portalUrl,
        window.location.origin,
      ).searchParams.get('token');
      if (!token) throw new Error('no portal token');
      return token;
    })().finally(() => {
      contactViewStart = null;
    });
  }
  return contactViewStart;
}

/**
 * The CRM-side shell of the portal forms (PORTAL-P3-ROLE-MENU): hands the signed-in salesperson's
 * portal slug (from /users/me) to the same portal components the `/portal/c/{slug}` tree renders.
 */
export function MySlug({
  children,
}: {
  children: (slug: string) => ReactNode;
}) {
  const { salesperson, isLoading, isError } = useAccountProfileForHeader();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const viewingAs = useImpersonationSession() !== null;
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
    // The token's own identity must be this salesperson's. The stored slug is only a hint, and
    // an impersonation token (this tab only) skips it: the device's stored slug is the admin's.
    const checkIdentity = () =>
      fetchMeWithGrace()
        .then((me) => {
          if (cancelled) return;
          if (me.portal_slug !== mySlug) {
            if (isImpersonationToken()) clearImpersonationToken();
            else dropToken();
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

    // Viewing as the salesperson with no token of its own in this tab: start the contact
    // impersonation here. The stored token and slug are the admin's own device sign-in and are
    // never cleared; a failed start sends the visitor to the code step.
    if (viewingAs && !isImpersonationToken()) {
      void (async () => {
        try {
          const token = await startContactViewOnce();
          // A run that was cancelled while the start was in flight writes nothing.
          if (cancelled) return;
          writePortalToken(token, { impersonation: true });
        } catch {
          if (!cancelled) toVerify();
          return;
        }
        if (!cancelled) await checkIdentity();
      })();
      return () => {
        cancelled = true;
      };
    }
    const impersonating = isImpersonationToken();
    const token = readPortalToken();
    // A token that is not this salesperson's (shared device) is dropped, as the portal slug page does.
    if (!token || (!impersonating && readPortalSlug() !== mySlug)) {
      if (token) dropToken();
      toVerify();
      return;
    }
    void checkIdentity();
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
