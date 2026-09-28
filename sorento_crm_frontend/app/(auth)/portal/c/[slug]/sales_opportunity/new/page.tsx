'use client';

import { use } from 'react';
import { useRouter } from 'next/navigation';
import SalesOpportunityPortalForm from '../../../../sales_opportunity/components/SalesOpportunityPortalForm';
import { portalDetailPath } from '../../../../lib/portal-paths';

export default function PortalSlugSalesOpportunityNewPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  const router = useRouter();
  return (
    <SalesOpportunityPortalForm
      onCreated={(id) => router.push(portalDetailPath('sales_opportunity', id, slug))}
    />
  );
}
