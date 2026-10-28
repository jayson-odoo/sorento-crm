'use client';

import { useRouter } from 'next/navigation';
import SalesOpportunityPortalForm from '@/app/(auth)/portal/sales_opportunity/components/SalesOpportunityPortalForm';
import { portalDetailPath } from '@/app/(auth)/portal/lib/portal-paths';
import { MySlug } from '../../MySlug';

export default function MyRequestsSalesOpportunityNewPage() {
  const router = useRouter();
  return (
    <MySlug>
      {(slug) => (
        <SalesOpportunityPortalForm
          onCreated={(id) => router.push(portalDetailPath('sales_opportunity', id, slug))}
        />
      )}
    </MySlug>
  );
}
