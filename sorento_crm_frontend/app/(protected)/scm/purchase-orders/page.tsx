import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import PurchaseOrdersList from './components/PurchaseOrdersList';

export const metadata: Metadata = {
  title: 'Purchase Orders',
  description: 'Inbound supply - the on-order record feeding net position.',
};

export default function PurchaseOrdersPage() {
  return (
    <>
      <Container>
        <PageHeader title="Purchase Orders" />
      </Container>

      <Container>
        <PurchaseOrdersList />
      </Container>
    </>
  );
}
