'use client';

/**
 * Legacy token-based verify page - identity recovered from a (possibly
 * expired) `?token=` via /token-info. The slug tree has its own verify page
 * at /portal/c/[slug]/verify that needs no token at all.
 */

import { Suspense } from 'react';
import { PortalVerifyCard } from '../components/PortalVerifyCard';

export default function PortalVerifyPage() {
  return (
    <Suspense fallback={null}>
      <PortalVerifyCard />
    </Suspense>
  );
}
