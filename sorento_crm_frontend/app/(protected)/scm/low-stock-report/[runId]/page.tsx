import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { LowStockReportView } from '../components/LowStockReportView';

export const metadata: Metadata = {
  title: 'Low stock report',
  description: 'One plan\'s low stock report, previewed before download.',
};

/**
 * One run's low stock report (PLAN-excel-preview-26sep AC-10): where the daily email's link
 * and Reorder Planning's Actions item land.
 */
export default async function LowStockReportRunPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  return (
    <RequireAccess permission="scm.reorder.run">
      <Container width="fluid">
        <LowStockReportView runId={runId} />
      </Container>
    </RequireAccess>
  );
}
