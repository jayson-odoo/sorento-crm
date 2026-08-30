import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import { SalesOrderDetailClient } from './components/SalesOrderDetailClient';

export const metadata: Metadata = {
  title: 'Sales order draft',
  description: 'What the system proposed, what it is unsure about, and what it refuses to publish.',
};

export default async function ProjectSalesOrderPage({
  params,
}: {
  params: Promise<{ projectId: string; psoId: string }>;
}) {
  const { projectId, psoId } = await params;
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6">
        <PageHeader title="Sales Order" />
        <SalesOrderDetailClient projectId={projectId} psoId={psoId} />
      </Container>
    </RequireAccess>
  );
}
