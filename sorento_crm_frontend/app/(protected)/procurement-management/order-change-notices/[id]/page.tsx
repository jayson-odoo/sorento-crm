import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import RecordEntityRegistrar from '@/components/common/RecordEntityRegistrar';
import OrderChangeNoticeDetail from '../components/OrderChangeNoticeDetail';

export const metadata: Metadata = {
  title: 'Order Change Notice',
  description: 'View an order change notice',
};

export default async function OrderChangeNoticeDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <Container>
      <PageHeader
        title="Order Change Notice"
        actions={
          <BackToList
            listPath="/procurement-management/order-change-notices"
            label="Back to order change notices"
            originLabel="Back to project"
          />
        }
      />
      <div className="mt-6">
        <RecordEntityRegistrar entityType="order_change_notice" id={id} />
        <OrderChangeNoticeDetail ocnId={id} />
      </div>
    </Container>
  );
}
