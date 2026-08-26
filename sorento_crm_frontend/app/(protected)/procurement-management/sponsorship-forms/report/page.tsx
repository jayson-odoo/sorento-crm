import { Suspense } from 'react';
import { Metadata } from 'next';
import { ReportPage } from '@/components/reports/ReportPage';

export const metadata: Metadata = {
  title: 'Sponsorship Report',
  description: 'Sponsorship report',
};

/**
 * The whole cost of putting a registered report on screen: a key and a breadcrumb.
 * Report #2 is this file again with a different key (PLAN-reporting-foundation).
 */
export default function SponsorshipReportPage() {
  return (
    <Suspense fallback={null}>
      <ReportPage
        reportKey="sponsorship"
        breadcrumb={[
          { label: 'Project Sales Admin' },
          { label: 'Sponsorship Forms', href: '/procurement-management/sponsorship-forms' },
          { label: 'Report' },
        ]}
      />
    </Suspense>
  );
}
