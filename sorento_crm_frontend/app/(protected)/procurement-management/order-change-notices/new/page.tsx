import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import OrderChangeNoticeForm from '../components/OrderChangeNoticeForm';

export const metadata: Metadata = {
  title: 'New Order Change Notice',
  description: 'Raise an order change notice',
};

export default async function NewOrderChangeNoticePage({
  searchParams,
}: {
  searchParams: Promise<{ project_id?: string }>;
}) {
  const { project_id } = await searchParams;
  return (
    <Container>
      <PageHeader title="New Order Change Notice" />
      <div className="mt-6">
        <OrderChangeNoticeForm projectId={project_id} />
      </div>
    </Container>
  );
}
