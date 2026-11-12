import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import { SparePartRequestForm } from '../../components/SparePartRequestForm';

export const metadata: Metadata = {
  title: 'Edit Spare Part Request',
};

export default async function EditSparePartRequestPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <RequireAccess permission="procurement.spare_part_requests.create">
      <Container>
        <PageHeader
          title="Edit spare part request"
          actions={
            <BackToList
              listPath={`/project-sales/order-inquiries/${id}`}
              label="Back to the request"
            />
          }
        />
      </Container>
      <Container className="space-y-6">
        <SparePartRequestForm id={id} />
      </Container>
    </RequireAccess>
  );
}
