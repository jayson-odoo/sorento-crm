import { Suspense } from 'react';
import { Metadata } from 'next';
import Link from 'next/link';
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
        belowHeader={
          <Link
            href="/sales/leaderboard?basis=invoiced&by=product"
            className="mt-2 inline-block text-sm text-primary hover:underline"
          >
            Product ranking
          </Link>
        }
      />
    </Suspense>
  );
}
