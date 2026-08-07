'use client';

/**
 * `/portal/lodge` - the prototype route, and now a signpost off it.
 *
 * **It hands you to the live journey when you have an identity.** This route was the S3
 * Phase 1 prototype: `?scenario=` picks a mocked extraction outcome and a tap on the photo
 * tile just increments a counter, because there is no backend behind it. That is fine as a
 * design surface and actively misleading as a destination - somebody who reached it while
 * holding a portal token attached photos, pressed Continue, and got a mocked warranty
 * verdict for a complaint that was never filed. Nothing on screen says so.
 *
 * So: a stored portal token plus a slug means there is a real journey to run, and the
 * visitor is sent to `/portal/c/{slug}/lodge` instead. The prototype stays reachable
 * deliberately, for reviewing states without a contact - either with no identity at all, or
 * explicitly via `?mock=1`, which is the honest way to ask for it.
 *
 * `?scenario=` selects which extraction outcome the MOCK exercises. Four are worth walking,
 * and three of them are normal traffic rather than error paths - 68% of receipts resolve, 8%
 * land mid-band, 24% carry no usable shop name:
 *
 *   /portal/lodge?mock=1                      resolved     (dealer matched exactly)
 *   /portal/lodge?mock=1&scenario=candidate   candidate    (matched, not well enough)
 *   /portal/lodge?mock=1&scenario=unmatched   unmatched    (no shop name printed at all)
 *   /portal/lodge?mock=1&scenario=dealer_track dealer track (a Sorento order number quoted)
 */

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

import { Skeleton } from '@/components/ui/skeleton';

import { LodgeFlow } from '../components/lodge/LodgeFlow';
import type { MockScenario } from '../components/lodge/lodgeMocks';
import { fetchMe, readPortalToken } from '../lib/portal-client';
import { portalLodgePath, readPortalSlug } from '../lib/portal-paths';

const SCENARIOS: MockScenario[] = ['resolved', 'candidate', 'unmatched', 'dealer_track'];

function LodgeContent() {
  const params = useSearchParams();
  const router = useRouter();
  const [decided, setDecided] = useState(false);

  const forceMock = params?.get('mock') === '1';

  useEffect(() => {
    if (forceMock) {
      setDecided(true);
      return;
    }
    if (!readPortalToken()) {
      // Nobody to file against. The prototype is the honest thing to show.
      setDecided(true);
      return;
    }

    const stored = readPortalSlug();
    if (stored) {
      router.replace(portalLodgePath(stored));
      return;
    }

    // A token with no stored slug is the IMPERSONATION case, and it is the common one:
    // `/portal` deliberately persists nothing on an admin's machine, so an admin viewing
    // the portal as a contact has a perfectly good token and no slug. Keying only on the
    // stored slug left exactly the people testing this stranded on the mock, which is the
    // bug this route was supposed to fix. Ask the token who it belongs to instead.
    let cancelled = false;
    fetchMe()
      .then((me) => {
        if (cancelled) return;
        const slug = (me.portal_slug || '').trim();
        if (slug) router.replace(portalLodgePath(slug));
        else setDecided(true);
      })
      .catch(() => {
        // Expired, revoked, or a contact with no slug. Falling back to the labelled
        // prototype beats a blank screen.
        if (!cancelled) setDecided(true);
      });
    return () => {
      cancelled = true;
    };
    // Intentional: decided once, on mount. A redirect mid-journey would be worse than the
    // prototype it is replacing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!decided) {
    return (
      <div className="mx-auto flex w-full max-w-xl flex-col gap-3 px-4 py-6 sm:max-w-2xl sm:px-6 lg:max-w-4xl">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-1 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  const requested = params?.get('scenario') as MockScenario | null;
  const scenario = requested && SCENARIOS.includes(requested) ? requested : 'resolved';
  return (
    <div className="flex flex-col">
      {/* Says what this is. The prototype's whole failure mode was looking exactly like
          the real thing while filing nothing. */}
      <p className="mx-auto w-full max-w-xl px-4 pt-4 text-xs text-muted-foreground sm:max-w-2xl sm:px-6 lg:max-w-4xl">
        Preview only - nothing submitted here is saved. Open the portal as a contact to file a
        real report.
      </p>
      <LodgeFlow key={scenario} scenario={scenario} />
    </div>
  );
}

export default function PortalLodgePage() {
  return (
    <Suspense fallback={null}>
      <LodgeContent />
    </Suspense>
  );
}
