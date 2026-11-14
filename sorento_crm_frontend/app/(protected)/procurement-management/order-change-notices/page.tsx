import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import OrderChangeNoticesList from './components/OrderChangeNoticesList';

export const metadata: Metadata = {
  title: 'Order Change Notices',
  description: 'Changes to customer orders',
};

export default function OrderChangeNoticesPage() {
  return (
    <>
      <Container>
        <PageHeader title="Order Change Notices" />
      </Container>

      <Container>
        <OrderChangeNoticesList />
      </Container>
    </>
  );
}
