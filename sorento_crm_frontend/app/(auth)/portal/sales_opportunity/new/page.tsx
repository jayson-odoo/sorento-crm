'use client';

import { useRouter } from 'next/navigation';
import SalesOpportunityPortalForm from '../components/SalesOpportunityPortalForm';

export default function PortalSalesOpportunityNewPage() {
  const router = useRouter();
  return (
    <SalesOpportunityPortalForm
      onCreated={(id) => router.push(`/portal/sales_opportunity/${id}`)}
    />
  );
}
