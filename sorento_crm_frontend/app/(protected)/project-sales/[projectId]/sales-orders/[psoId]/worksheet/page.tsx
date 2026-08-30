import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { projectCrumbs } from '@/app/(protected)/project-sales/_shared/lib/crumbs';
import RequireAccess from '@/app/components/common/RequireAccess';
import { SalesOrderWorksheetClient } from './components/SalesOrderWorksheetClient';

export const metadata: Metadata = {
  title: 'AutoCount SO worksheet',
  description: 'The sales order as AutoCount will read it.',
};

export default async function ProjectSalesOrderWorksheetPage({
  params,
}: {
  params: Promise<{ projectId: string; psoId: string }>;
}) {
  const { projectId, psoId } = await params;
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6">
        <PageHeader
          title="Worksheet"
          crumbs={projectCrumbs(
            projectId,
            { title: 'Sales Order', path: `/project-sales/${projectId}/sales-orders/${psoId}` },
            { title: 'Worksheet' },
          )}
        />
        <SalesOrderWorksheetClient projectId={projectId} psoId={psoId} />
      </Container>
    </RequireAccess>
  );
}
