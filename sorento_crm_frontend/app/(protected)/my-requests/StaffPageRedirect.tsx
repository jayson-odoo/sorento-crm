'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

/** A MY REQUESTS link for a form that now opens on its staff page (PORTAL-P4-REQUESTS). */
export function StaffPageRedirect({ to }: { to: string }) {
  const router = useRouter();
  useEffect(() => {
    router.replace(to);
  }, [router, to]);
  return null;
}
