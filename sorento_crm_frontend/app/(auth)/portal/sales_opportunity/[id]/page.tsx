'use client';

import { use } from 'react';
import SalesOpportunityPortalDetail from '../components/SalesOpportunityPortalDetail';

export default function PortalSalesOpportunityDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <SalesOpportunityPortalDetail id={id} />;
}
