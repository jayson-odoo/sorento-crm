import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import { OrderInquiryDetail } from './components/OrderInquiryDetail';

export const metadata: Metadata = {
  title: 'Order Inquiry',
  description: 'One sales order, everything purchasing has been told to buy for it.',
};

export default async function OrderInquiryDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <RequireAccess permission="projects.projects.view">
      <Container>
        <PageHeader
          title="Order Inquiry"
          actions={
            <BackToList
              listPath="/project-sales/order-inquiries"
              label="Back to order inquiries"
            />
          }
        />
      </Container>
      <Container className="space-y-6">
        <OrderInquiryDetail id={id} />
      </Container>
    </RequireAccess>
  );
}
