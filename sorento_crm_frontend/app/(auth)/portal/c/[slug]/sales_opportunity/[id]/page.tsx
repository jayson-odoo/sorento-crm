'use client';

import { use } from 'react';
import SalesOpportunityPortalDetail from '../../../../sales_opportunity/components/SalesOpportunityPortalDetail';

export default function PortalSlugSalesOpportunityDetailPage({
  params,
}: {
  params: Promise<{ slug: string; id: string }>;
}) {
  const { slug, id } = use(params);
  return <SalesOpportunityPortalDetail id={id} slug={slug} />;
}
