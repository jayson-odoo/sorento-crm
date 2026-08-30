import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { projectCrumbs } from '@/app/(protected)/project-sales/_shared/lib/crumbs';
import RequireAccess from '@/app/components/common/RequireAccess';
import { OrderInquiryClient } from './components/OrderInquiryClient';

export const metadata: Metadata = {
  title: 'Order inquiry',
  description: 'What purchasing has been told to buy, hold or change on this project.',
};

export default async function ProjectOrderInquiryPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6">
        <PageHeader
          title="Order Inquiries"
          crumbs={projectCrumbs(projectId, { title: 'Order Inquiries' })}
        />
        <OrderInquiryClient projectId={projectId} />
      </Container>
    </RequireAccess>
  );
}
