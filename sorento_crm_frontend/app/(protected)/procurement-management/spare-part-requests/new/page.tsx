import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import { SparePartRequestForm } from '@/app/(protected)/project-sales/order-inquiries/spare-part-requests/components/SparePartRequestForm';

export const metadata: Metadata = {
  title: 'New Order Request',
};

export default function NewSparePartRequestPage() {
  return (
    <RequireAccess permission="procurement.spare_part_requests.create">
      <Container>
        <PageHeader
          title="New Order Request"
          actions={
            <BackToList
              listPath="/procurement-management/spare-part-requests"
              label="Back to order requests"
            />
          }
        />
      </Container>
      <Container className="space-y-6">
        <SparePartRequestForm />
      </Container>
    </RequireAccess>
  );
}
