'use client';

import { use, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { portalHomePath } from '../../../lib/portal-paths';

/** Fix round 5: Customer asks is a kind on the landing now; an old link lands on it. */
export default function PortalSlugCustomerAsksPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  const router = useRouter();
  useEffect(() => {
    router.replace(portalHomePath({ slug, type: 'customer_asks' }));
  }, [router, slug]);
  return null;
}
