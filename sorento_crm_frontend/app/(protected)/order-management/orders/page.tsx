import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import OrdersList from './components/OrdersList';

export const metadata: Metadata = {
  title: 'Delivery Orders',
  description: 'Manage delivery orders.',
};

export default async function OrdersPage() {
  return (
    <>
      <Container>
        <PageHeader title="Delivery Orders" />
      </Container>

      <Container>
        <OrdersList />
      </Container>
    </>
  );
}
