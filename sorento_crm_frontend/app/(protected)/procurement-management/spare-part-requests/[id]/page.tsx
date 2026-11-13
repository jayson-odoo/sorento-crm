import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import { SparePartRequestRecord } from '../components/SparePartRequestRecord';

export const metadata: Metadata = {
  title: 'Spare Part Request',
};

export default async function SparePartRequestPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <RequireAccess anyPermission={['projects.projects.view', 'procurement.spare_part_requests.create']}>
      <Container>
        <PageHeader
          title="Spare Part Request"
          actions={
            <BackToList
              listPath="/procurement-management/spare-part-requests"
              label="Back to spare part requests"
            />
          }
        />
      </Container>
      <Container className="space-y-6">
        <SparePartRequestRecord id={id} />
      </Container>
    </RequireAccess>
  );
}
