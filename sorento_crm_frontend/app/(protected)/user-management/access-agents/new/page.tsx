'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

/**
 * Redirect /new to list page. Create is now done via modal on the list.
 */
export default function NewAccessAgentPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/user-management/access-agents');
  }, [router]);
  return null;
}
