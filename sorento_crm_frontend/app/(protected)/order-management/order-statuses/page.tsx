import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import OrderStatusesList from './components/OrderStatusesList';

export const metadata: Metadata = {
  title: 'Delivery Order Statuses',
  description: 'Manage delivery order statuses.',
};

export default async function OrderStatusesPage() {
  return (
    <>
      <Container>
        <PageHeader title="Delivery Order Statuses" />
      </Container>

      <Container>
        <OrderStatusesList />
      </Container>
    </>
  );
}
