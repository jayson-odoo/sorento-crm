import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { SPARE_PART_READ_PERMISSIONS } from '@/app/(protected)/project-sales/_shared/lib/sparePartRequest';
import { OrderInquiryHeadersOrLinesView } from './components/OrderInquiryHeadersOrLinesView';

export const metadata: Metadata = {
  title: 'Order Inquiries',
  description: 'Everything purchasing has been told to buy.',
};

export default function OrderInquiriesPage() {
  return (
    <RequireAccess anyPermission={['projects.projects.view', ...SPARE_PART_READ_PERMISSIONS]}>
      <Container className="space-y-6">
        <OrderInquiryHeadersOrLinesView />
      </Container>
    </RequireAccess>
  );
}
