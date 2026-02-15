'use client';

import { use, useEffect } from 'react';
import { useRouter } from 'next/navigation';

/**
 * Redirect /[id]/edit to detail page. Edit is now done via modal on the detail page.
 */
export default function EditAccessAgentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  useEffect(() => {
    router.replace(`/user-management/access-agents/${id}`);
  }, [router, id]);
  return null;
}
