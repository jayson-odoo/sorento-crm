'use client';

/**
 * Stable per-contact portal URL - `/portal/c/{slug}`.
 *
 * The slug is an identity hint, not a credential: with a live device token
 * for this contact the landing renders straight away; otherwise a signed-in
 * CRM user opening their OWN contact's portal is let in by the CRM-session
 * bridge, and everyone else verifies via OTP. When the device holds a token
 * for a DIFFERENT contact (shared device), the slug in the address bar wins -
 * the stored session is dropped first.
 */

import { Suspense, use, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Skeleton } from '@/components/ui/skeleton';
import { PortalLanding } from '../../components/PortalLanding';
import { getSession } from 'next-auth/react';
import {
  clearPortalToken,
  openPortalFromCrm,
  readPortalToken,
  writePortalToken,
} from '../../lib/portal-client';
import {
  clearPortalSlug,
  portalVerifyPath,
  readPortalSlug,
  writePortalSlug,
} from '../../lib/portal-paths';

function SlugEntry({ slug }: { slug: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [ready, setReady] = useState(false);
  // One bridge call per visit: Strict Mode's second effect run must not mint a second token.
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const token = readPortalToken();
    const storedSlug = readPortalSlug();
    const type = searchParams?.get('type');

    if (token && storedSlug && storedSlug !== slug) {
      // Slug wins: the visitor explicitly opened another contact's URL. Drop
      // the previous session entirely (token AND slug pointer) so no stale
      // identity survives on this device.
      clearPortalToken();
      clearPortalSlug();
    } else if (token) {
      if (!storedSlug) writePortalSlug(slug);
      setReady(true);
      return;
    }

    void (async () => {
      let bridged: { token: string } | null = null;
      try {
        if (await getSession()) bridged = await openPortalFromCrm(slug);
      } catch {
        bridged = null;
      }
      if (bridged) {
        writePortalToken(bridged.token);
        writePortalSlug(slug);
        setReady(true);
        return;
      }
      router.replace(portalVerifyPath({ slug, type }));
    })();
    // Intentional: only on first mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!ready) {
    return (
      <div className="w-full px-3 pt-4 pb-4 space-y-3">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return <PortalLanding slug={slug} />;
}

export default function PortalSlugPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  return (
    <Suspense fallback={null}>
      <SlugEntry slug={slug} />
    </Suspense>
  );
}
