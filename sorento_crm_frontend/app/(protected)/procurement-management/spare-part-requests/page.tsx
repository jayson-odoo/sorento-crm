import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { PageHeader } from '@/components/common/PageHeader';
import { SparePartRequestsList } from './components/SparePartRequestsList';

export const metadata: Metadata = {
  title: 'Spare Part Requests',
};

/** SPARE-PART-ORDER-REQUEST (G3): who reads it as the request's API does (create grant, or
 *  the order inquiry view an approver holds); the server scopes the rows. */
export default function SparePartRequestsPage() {
  return (
    <RequireAccess anyPermission={['projects.projects.view', 'procurement.spare_part_requests.create']}>
      <Container>
        <PageHeader title="Spare Part Requests" />
      </Container>
      <Container>
        <SparePartRequestsList />
      </Container>
    </RequireAccess>
  );
}
