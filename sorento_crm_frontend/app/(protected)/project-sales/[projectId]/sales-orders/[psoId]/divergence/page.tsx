import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { projectCrumbs } from '@/app/(protected)/project-sales/_shared/lib/crumbs';
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
        <PageHeader
          title="AutoCount Comparison"
          crumbs={projectCrumbs(
            projectId,
            { title: 'Sales Order', path: `/project-sales/${projectId}/sales-orders/${psoId}` },
            { title: 'AutoCount Comparison' },
          )}
        />
        <DivergenceReviewClient projectId={projectId} psoId={psoId} />
      </Container>
    </RequireAccess>
  );
}
