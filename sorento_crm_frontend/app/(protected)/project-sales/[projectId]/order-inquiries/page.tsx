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
              <BreadcrumbPage>Order inquiry</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <OrderInquiryClient projectId={projectId} />
      </Container>
    </RequireAccess>
  );
}
