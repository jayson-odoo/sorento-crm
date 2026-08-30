import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { projectCrumbs } from '@/app/(protected)/project-sales/_shared/lib/crumbs';
import RequireAccess from '@/app/components/common/RequireAccess';
import { AmendmentReviewClient } from './components/AmendmentReviewClient';

export const metadata: Metadata = {
  title: 'Revision review',
  description: 'The difference between the version this order was built from and a newer one.',
};

export default async function ProjectSalesOrderRevisionsPage({
  params,
}: {
  params: Promise<{ projectId: string; psoId: string }>;
}) {
  const { projectId, psoId } = await params;
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6">
        <PageHeader
          title="Revision Review"
          crumbs={projectCrumbs(
            projectId,
            { title: 'Sales Order', path: `/project-sales/${projectId}/sales-orders/${psoId}` },
            { title: 'Revision Review' },
          )}
        />
        <AmendmentReviewClient projectId={projectId} psoId={psoId} />
      </Container>
    </RequireAccess>
  );
}
