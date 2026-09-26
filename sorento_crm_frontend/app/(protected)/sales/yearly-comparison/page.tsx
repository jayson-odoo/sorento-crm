import { Suspense } from 'react';
import { Metadata } from 'next';
import { ReportPage } from '@/components/reports/ReportPage';

export const metadata: Metadata = {
  title: 'Yearly Comparison',
  description: 'Yearly sales comparison',
};

/** Report #2 on the kernel: the sponsorship route wrapper with a new key. */
export default function YearlyComparisonPage() {
  return (
    <Suspense fallback={null}>
      <ReportPage
        reportKey="sales_yearly"
        breadcrumb={[{ label: 'Sales' }, { label: 'Yearly comparison' }]}
      />
    </Suspense>
  );
}
