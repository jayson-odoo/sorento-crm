'use client';

/**
 * Stable per-contact portal URL — `/portal/c/{slug}`.
 *
 * The slug is an identity hint, not a credential: with a live device token
 * for this contact the landing renders straight away; otherwise the user
 * verifies via OTP. When the device holds a token for a DIFFERENT contact
 * (shared device), the slug in the address bar wins — the stored session is
 * dropped and this contact verifies fresh.
 */

import { Suspense, use, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Skeleton } from '@/components/ui/skeleton';
import { PortalLanding } from '../../components/PortalLanding';
import { clearPortalToken, readPortalToken } from '../../lib/portal-client';
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

  useEffect(() => {
    const token = readPortalToken();
    const storedSlug = readPortalSlug();
    const type = searchParams?.get('type');

    if (!token) {
      router.replace(portalVerifyPath({ slug, type }));
      return;
    }
    if (storedSlug && storedSlug !== slug) {
      // Slug wins: the visitor explicitly opened another contact's URL. Drop
      // the previous session entirely (token AND slug pointer) so no stale
      // identity survives on this device.
      clearPortalToken();
      clearPortalSlug();
      router.replace(portalVerifyPath({ slug, type }));
      return;
    }
    if (!storedSlug) writePortalSlug(slug);
    setReady(true);
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
