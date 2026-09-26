import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { LowStockReportView } from './components/LowStockReportView';

export const metadata: Metadata = {
  title: 'Low stock report',
  description: 'The newest plan\'s low stock report, previewed before download.',
};

/** The sidebar's page (PLAN-excel-preview-26sep AC-16b): the newest completed run. */
export default function LowStockReportPage() {
  return (
    <RequireAccess permission="scm.reorder.run">
      <Container width="fluid">
        <LowStockReportView />
      </Container>
    </RequireAccess>
  );
}
