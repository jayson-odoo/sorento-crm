'use client';

import { use } from 'react';
import SalesOpportunityPortalDetail from '@/app/(auth)/portal/sales_opportunity/components/SalesOpportunityPortalDetail';
import { MySlug } from '../../MySlug';

export default function MyRequestsSalesOpportunityDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <MySlug>{(slug) => <SalesOpportunityPortalDetail id={id} slug={slug} />}</MySlug>;
}
