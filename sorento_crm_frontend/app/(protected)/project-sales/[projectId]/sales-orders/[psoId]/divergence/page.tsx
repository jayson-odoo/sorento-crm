import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import { DivergenceReviewClient } from './components/DivergenceReviewClient';

export const metadata: Metadata = {
  title: 'AutoCount comparison',
  description:
    'Where AutoCount disagrees with the sales order we published, line by line, and which side wins.',
};

export default async function ProjectSalesOrderDivergencePage({
  params,
}: {
  params: Promise<{ projectId: string; psoId: string }>;
}) {
  const { projectId, psoId } = await params;
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6">
        <PageHeader title="AutoCount Comparison" />
        <DivergenceReviewClient projectId={projectId} psoId={psoId} />
      </Container>
    </RequireAccess>
  );
}
