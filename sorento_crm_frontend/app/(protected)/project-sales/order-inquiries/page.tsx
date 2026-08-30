import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { OrderInquiriesClient } from './components/OrderInquiriesClient';

export const metadata: Metadata = {
  title: 'Order Inquiries',
  description: 'Everything purchasing has been told to buy.',
};

export default function OrderInquiriesPage() {
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6">
        <OrderInquiriesClient />
      </Container>
    </RequireAccess>
  );
}
