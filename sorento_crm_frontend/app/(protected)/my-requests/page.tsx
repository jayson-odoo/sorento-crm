'use client';

import { Suspense } from 'react';
import { PortalLanding } from '@/app/(auth)/portal/components/PortalLanding';
import { MySlug } from './MySlug';

export default function MyRequestsPage() {
  return (
    <MySlug>
      {(slug) => (
        <Suspense fallback={null}>
          <PortalLanding slug={slug} embedded />
        </Suspense>
      )}
    </MySlug>
  );
}
