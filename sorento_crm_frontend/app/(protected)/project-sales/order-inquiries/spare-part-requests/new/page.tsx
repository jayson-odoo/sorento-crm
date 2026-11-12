import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import { SparePartRequestForm } from '../components/SparePartRequestForm';

export const metadata: Metadata = {
  title: 'New Spare Part Request',
};

export default function NewSparePartRequestPage() {
  return (
    <RequireAccess permission="procurement.spare_part_requests.create">
      <Container>
        <PageHeader
          title="New spare part request"
          actions={
            <BackToList listPath="/project-sales/order-inquiries" label="Back to order inquiries" />
          }
        />
      </Container>
      <Container className="space-y-6">
        <SparePartRequestForm />
      </Container>
    </RequireAccess>
  );
}
