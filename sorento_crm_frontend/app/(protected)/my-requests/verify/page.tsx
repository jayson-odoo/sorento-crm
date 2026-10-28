'use client';

import { Suspense, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { PortalVerifyCard } from '@/app/(auth)/portal/components/PortalVerifyCard';
import { useAccountProfileForHeader } from '@/hooks/useAccountProfileForHeader';
import { useImpersonationSession } from '@/lib/impersonation-store';

export default function MyRequestsVerifyPage() {
  const { salesperson, isLoading, isError } = useAccountProfileForHeader();
  const impersonating = useImpersonationSession() !== null;
  const router = useRouter();
  const missing = !isLoading && (!salesperson || isError);

  // Never stuck: not a salesperson, or the profile read failed -> the CRM home.
  useEffect(() => {
    if (missing) router.replace('/');
  }, [missing, router]);

  if (!salesperson || isError) return null;
  return (
    <Suspense fallback={null}>
      {/* No automatic WhatsApp code to the salesperson while an admin views as them. */}
      <PortalVerifyCard slug={salesperson.portalSlug} autoSend={!impersonating} />
    </Suspense>
  );
}
