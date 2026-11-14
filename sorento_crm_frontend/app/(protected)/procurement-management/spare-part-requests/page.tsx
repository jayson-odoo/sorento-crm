import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { SPARE_PART_READ_PERMISSIONS } from '@/app/(protected)/project-sales/_shared/lib/sparePartRequest';
import { PageHeader } from '@/components/common/PageHeader';
import { SparePartRequestsList } from './components/SparePartRequestsList';

export const metadata: Metadata = {
  title: 'Order Requests',
};

/** SPARE-PART-ORDER-REQUEST (G3): who reads it as the request's API does (a spare part grant,
 *  or the order inquiry view); the server scopes the rows. */
export default function SparePartRequestsPage() {
  return (
    <RequireAccess anyPermission={['projects.projects.view', ...SPARE_PART_READ_PERMISSIONS]}>
      <Container>
        <PageHeader title="Order Requests" />
      </Container>
      <Container>
        <SparePartRequestsList />
      </Container>
    </RequireAccess>
  );
}
