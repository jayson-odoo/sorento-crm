import { Suspense } from 'react';
import { Metadata } from 'next';
import { ReportPage } from '@/components/reports/ReportPage';

export const metadata: Metadata = {
  title: 'Top selling items',
  description: 'Top selling items',
};

export default function TopSellingItemsPage() {
  return (
    <Suspense fallback={null}>
      <ReportPage
        reportKey="top_selling_items"
        breadcrumb={[{ label: 'Sales' }, { label: 'Top selling items' }]}
      />
    </Suspense>
  );
}
