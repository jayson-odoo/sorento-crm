'use client';

import { Suspense } from 'react';
import { PortalVerifyCard } from '@/app/(auth)/portal/components/PortalVerifyCard';
import { useAccountProfileForHeader } from '@/hooks/useAccountProfileForHeader';

export default function MyRequestsVerifyPage() {
  const { salesperson } = useAccountProfileForHeader();
  if (!salesperson) return null;
  return (
    <Suspense fallback={null}>
      <PortalVerifyCard slug={salesperson.portalSlug} />
    </Suspense>
  );
}
