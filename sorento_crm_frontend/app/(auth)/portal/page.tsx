'use client';

/**
 * Legacy `/portal` entry — thin resolver in front of the stable slug tree.
 *
 * - `?token=` links (old WhatsApp messages, impersonation) land here: the
 *   token is stored, then the contact's slug is resolved and the browser is
 *   redirected to `/portal/c/{slug}` so the address bar becomes the
 *   bookmarkable per-contact URL.
 * - Impersonation sessions stay on this legacy tree (sessionStorage token,
 *   no slug, nothing persisted on the admin's machine).
 * - No token anywhere → "get your portal link" card (WhatsApp CTA).
 */

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Skeleton } from '@/components/ui/skeleton';
import { PortalLanding } from './components/PortalLanding';
import { PortalVerifyCard } from './components/PortalVerifyCard';
import {
  PortalUnauthorizedError,
  demoteTokenToSession,
  fetchMeWithGrace,
  isImpersonationToken,
  readPortalToken,
  writePortalToken,
} from './lib/portal-client';
import {
  portalHomePath,
  portalVerifyPath,
  readPortalSlug,
  writePortalSlug,
} from './lib/portal-paths';

type Mode = 'boot' | 'legacy-landing' | 'request-link';

function PortalRootContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [mode, setMode] = useState<Mode>('boot');

  useEffect(() => {
    let cancelled = false;

    (async () => {
      // 1. Intake a `?token=` link. Impersonation tokens are session-scoped.
      const incoming = searchParams?.get('token');
      const isImpersonation = searchParams?.get('impersonation') === '1';
      if (incoming) {
        writePortalToken(incoming, { impersonation: isImpersonation });
        const url = new URL(window.location.href);
        url.searchParams.delete('token');
        url.searchParams.delete('impersonation');
        router.replace(url.pathname + (url.search ? url.search : ''));
      }

      const type = searchParams?.get('type');
      const token = incoming || readPortalToken();

      // 2. No identity at all → maybe a stored slug from a past visit can
      //    take over; otherwise offer the WhatsApp link-request CTA.
      if (!token) {
        const storedSlug = readPortalSlug();
        if (storedSlug) {
          router.replace(portalHomePath({ slug: storedSlug, type }));
          return;
        }
        if (!cancelled) setMode('request-link');
        return;
      }

      // 3. Resolve the contact behind the token → slug → stable URL. Grace
      //    retry absorbs the post-verify commit-visibility race so a fresh
      //    token isn't bounced straight back to the verify page.
      try {
        const me = await fetchMeWithGrace();
        if (cancelled) return;
        if (isImpersonation || me.impersonation) {
          // Defensive: if an impersonation link lacked the marker, make sure
          // the token does not persist beyond this tab.
          if (!isImpersonationToken()) demoteTokenToSession();
          setMode('legacy-landing');
          return;
        }
        const slug = (me.portal_slug || '').trim();
        if (!slug) {
          // Extremely unlikely (BE lazily mints on /me) — stay on the legacy
          // tree rather than break the session.
          setMode('legacy-landing');
          return;
        }
        writePortalSlug(slug);
        router.replace(portalHomePath({ slug, type }));
      } catch (e) {
        if (cancelled) return;
        if (e instanceof PortalUnauthorizedError) {
          // Expired/revoked token — recover via the legacy verify page, which
          // can look the contact up from the dead token.
          router.replace(
            portalVerifyPath({ slug: null, reason: 'expired', token, type }),
          );
          return;
        }
        setMode('request-link');
      }
    })();

    return () => {
      cancelled = true;
    };
    // Intentional: only on first mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (mode === 'legacy-landing') {
    return <PortalLanding />;
  }

  if (mode === 'request-link') {
    // No slug + no token: PortalVerifyCard renders the link-request CTA.
    return <PortalVerifyCard />;
  }

  return (
    <div className="w-full px-3 pt-4 pb-4 space-y-3">
      <Skeleton className="h-10 w-48" />
      <Skeleton className="h-12 w-full" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

export default function PortalPage() {
  return (
    <Suspense fallback={null}>
      <PortalRootContent />
    </Suspense>
  );
}
