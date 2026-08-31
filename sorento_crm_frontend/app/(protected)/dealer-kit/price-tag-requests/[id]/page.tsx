import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import PriceTagRequestDetail from '../components/PriceTagRequestDetail';

export const metadata: Metadata = {
  title: 'Price Tag Request Details',
  description: 'View price tag request details',
};

export default async function PriceTagRequestDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  // The breadcrumb and the Back button live INSIDE the detail component, not
  // here: the breadcrumb's leaf is the request's DOC NUMBER, and this server
  // component holds only the id, which is a UUID and may never reach a screen.
  return (
    <Container>
      <PriceTagRequestDetail requestId={id} />
    </Container>
  );
}
