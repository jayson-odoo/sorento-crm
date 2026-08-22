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
              {/* Not "Draft": this page is reached most often from a PUBLISHED order, and
                  a crumb that calls it a draft contradicts the status pill beside the
                  reference on the screen. The reference itself is not available here -
                  the page is a server component and the worksheet is fetched below. */}
              <BreadcrumbLink href={`/project-sales/${projectId}/sales-orders/${psoId}`}>
                Sales order
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Worksheet</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <SalesOrderWorksheetClient projectId={projectId} psoId={psoId} />
      </Container>
    </RequireAccess>
  );
}
