'use client';

/**
 * The consumer intake journey, live - `/portal/c/{slug}/lodge`.
 *
 * The token-scoped twin of the `?scenario=` prototype at `/portal/lodge`. Same component,
 * a different `LodgeBackend`: one interface, two implementations, never two copies of the
 * screens. A forked component is how a demo and the real thing quietly stop agreeing
 * about what the journey is.
 *
 * **Why it lives under the slug.** The token establishes who this is, so the phone number
 * and the name are never asked for - Phase 0's rule that anything knowable is never asked.
 * It also means the write endpoint has a real principal: an unauthenticated lodge route is
 * an invitation to fill the complaint table with junk.
 *
 * No token, or a token for a different contact, sends the visitor to OTP exactly as the
 * landing page does. The slug in the address bar wins on a shared device.
 */

import { Suspense, use, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

import { Skeleton } from '@/components/ui/skeleton';

import { LodgeFlow } from '../../../components/lodge/LodgeFlow';
import { liveLodgeBackend } from '../../../components/lodge/lodgeBackend';
import {
  fetchMe,
  PortalUnauthorizedError,
  readPortalToken,
  type PortalContact,
} from '../../../lib/portal-client';
import { portalVerifyPath, readPortalSlug, writePortalSlug } from '../../../lib/portal-paths';

function LiveLodge({ slug }: { slug: string }) {
  const router = useRouter();
  const [contact, setContact] = useState<PortalContact | null>(null);

  useEffect(() => {
    const token = readPortalToken();
    if (!token) {
      router.replace(portalVerifyPath({ slug }));
      return;
    }
    const storedSlug = readPortalSlug();
    if (storedSlug && storedSlug !== slug) {
      router.replace(portalVerifyPath({ slug }));
      return;
    }
    if (!storedSlug) writePortalSlug(slug);

    let cancelled = false;
    fetchMe()
      .then((me) => {
        if (!cancelled) setContact(me);
      })
      .catch((error) => {
        // An expired or revoked token is the ordinary case here, not an exception: the
        // consumer followed a WhatsApp link that may be weeks old.
        if (error instanceof PortalUnauthorizedError) router.replace(portalVerifyPath({ slug }));
      });
    return () => {
      cancelled = true;
    };
    // Intentional: only on first mount, mirroring the landing page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug]);

  if (!contact) {
    return (
      <div className="mx-auto flex w-full max-w-xl flex-col gap-3 px-4 py-6">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-1 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  return (
    <LodgeFlow
      live
      backend={liveLodgeBackend}
      contact={{ phone: contact.phone_number, name: contact.name }}
    />
  );
}

export default function PortalLodgeLivePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  return (
    <Suspense fallback={null}>
      <LiveLodge slug={slug} />
    </Suspense>
  );
}
