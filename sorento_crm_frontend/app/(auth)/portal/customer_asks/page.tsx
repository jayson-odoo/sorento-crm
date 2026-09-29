'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { portalHomePath } from '../lib/portal-paths';

/** Fix round 5: Customer asks is a kind on the landing now; an old link lands on it. */
export default function PortalCustomerAsksPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace(portalHomePath({ slug: null, type: 'customer_asks' }));
  }, [router]);
  return null;
}
