import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import { PurchaseOrderDetail } from './components/PurchaseOrderDetail';

export const metadata: Metadata = {
  title: 'Purchase Order',
  description: 'Purchase order detail - header, lines and goods receipt.',
};

export default async function PurchaseOrderDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <>
      <Container>
        <PageHeader
          title="Purchase Order"
          actions={
            <BackToList listPath="/scm/purchase-orders" label="Back to purchase orders" />
          }
        />
      </Container>

      <Container>
        <PurchaseOrderDetail id={id} />
      </Container>
    </>
  );
}
