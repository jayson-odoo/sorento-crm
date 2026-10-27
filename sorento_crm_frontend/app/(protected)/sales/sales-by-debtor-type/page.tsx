import { Suspense } from 'react';
import { Metadata } from 'next';
import { ReportPage } from '@/components/reports/ReportPage';

export const metadata: Metadata = {
  title: 'Sales by debtor type',
  description: 'Sales by debtor type by sales agent',
};

export default function SalesByDebtorTypePage() {
  return (
    <Suspense fallback={null}>
      <ReportPage
        reportKey="sales_by_debtor_type"
        breadcrumb={[{ label: 'Sales' }, { label: 'Sales by debtor type' }]}
      />
    </Suspense>
  );
}
