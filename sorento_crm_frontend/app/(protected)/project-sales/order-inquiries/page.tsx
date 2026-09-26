import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { OrderInquiryHeadersOrLinesView } from './components/OrderInquiryHeadersOrLinesView';

export const metadata: Metadata = {
  title: 'Order Inquiries',
  description: 'Everything purchasing has been told to buy.',
};

export default function OrderInquiriesPage() {
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6">
        <OrderInquiryHeadersOrLinesView />
      </Container>
    </RequireAccess>
  );
}
