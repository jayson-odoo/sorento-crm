'use client';

/**
 * Slug-based verify page - identity comes from the stable slug, no token
 * needed. This is what makes the bookmarked URL work on a brand-new device.
 */

import { Suspense, use } from 'react';
import { PortalVerifyCard } from '../../../components/PortalVerifyCard';

export default function PortalSlugVerifyPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  return (
    <Suspense fallback={null}>
      <PortalVerifyCard slug={slug} />
    </Suspense>
  );
}
