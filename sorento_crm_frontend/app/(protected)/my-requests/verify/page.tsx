'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

/** The WhatsApp code step belongs to the portal; inside the CRM an old link goes home. */
export default function MyRequestsVerifyPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/');
  }, [router]);
  return null;
}
