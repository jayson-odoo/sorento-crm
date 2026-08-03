'use client';

/**
 * S3 Phase 1 prototype route - the consumer intake journey, on mocks.
 *
 * Deliberately OUTSIDE the `/portal/c/[slug]` tree for now: this phase is about tuning the
 * flow and its states, and hanging it off a contact slug would force a real token before a
 * single screen could be reviewed. Phase 2 moves it under the slug tree, where the OTP
 * already establishes who the consumer is.
 *
 * `?scenario=` selects which extraction outcome to exercise. Four are worth walking, and
 * three of them are normal traffic rather than error paths - 68% of receipts resolve, 8%
 * land mid-band, 24% carry no usable shop name:
 *
 *   /portal/lodge                      resolved     (dealer matched exactly)
 *   /portal/lodge?scenario=candidate   candidate    (matched something, not well enough)
 *   /portal/lodge?scenario=unmatched   unmatched    (no shop name printed at all)
 *   /portal/lodge?scenario=dealer_track dealer track (a Sorento order number was quoted)
 */

import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';

import { LodgeFlow } from '../components/lodge/LodgeFlow';
import type { MockScenario } from '../components/lodge/lodgeMocks';

const SCENARIOS: MockScenario[] = ['resolved', 'candidate', 'unmatched', 'dealer_track'];

function LodgeContent() {
  const params = useSearchParams();
  const requested = params?.get('scenario') as MockScenario | null;
  const scenario = requested && SCENARIOS.includes(requested) ? requested : 'resolved';
  return <LodgeFlow key={scenario} scenario={scenario} />;
}

export default function PortalLodgePage() {
  return (
    <Suspense fallback={null}>
      <LodgeContent />
    </Suspense>
  );
}
