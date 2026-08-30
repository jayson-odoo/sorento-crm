import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
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
        <PageHeader title="Purchase Order" />
        <PurchaseOrderDetailClient projectId={projectId} poId={poId} />
      </Container>
    </RequireAccess>
  );
}
