import { Metadata } from 'next';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Container } from '@/components/common/container';
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
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink href="/">Home</BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbLink href="/project-sales/pipeline">Project Sales</BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbLink href={`/project-sales/${projectId}?tab=sales-orders`}>
                Sales orders
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbLink href={`/project-sales/${projectId}/sales-orders/${psoId}`}>
                Draft
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Revision</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <AmendmentReviewClient projectId={projectId} psoId={psoId} />
      </Container>
    </RequireAccess>
  );
}
