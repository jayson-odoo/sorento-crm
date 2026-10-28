'use client';

import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { PortalLanding } from '@/app/(auth)/portal/components/PortalLanding';
import { myRequestStaffPath } from '@/lib/my-requests-staff-pages';
import { MySlug } from './MySlug';
import { StaffPageRedirect } from './StaffPageRedirect';

export default function MyRequestsPage() {
  const staffList = myRequestStaffPath(useSearchParams()?.get('type'));
  if (staffList) return <StaffPageRedirect to={staffList} />;
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
