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
import { PurchaseOrderDetailClient } from './components/PurchaseOrderDetailClient';

export const metadata: Metadata = {
  title: 'Customer purchase order',
  description: 'One customer PO: its documents, its lines, and what it is ready to produce.',
};

/**
 * `pos/[poId]`, not `purchase-orders/[poId]`: that segment is already the PO DOCUMENT confirm
 * screen (`purchase-orders/[versionId]`), and two dynamic segments cannot share a parent.
 * The tab is called POs, so the URL says the same.
 */
export default async function ProjectPurchaseOrderPage({
  params,
}: {
  params: Promise<{ projectId: string; poId: string }>;
}) {
  const { projectId, poId } = await params;
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6 pb-64">
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
              <BreadcrumbLink href={`/project-sales/${projectId}?tab=pos`}>POs</BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Purchase order</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <PurchaseOrderDetailClient projectId={projectId} poId={poId} />
      </Container>
    </RequireAccess>
  );
}
