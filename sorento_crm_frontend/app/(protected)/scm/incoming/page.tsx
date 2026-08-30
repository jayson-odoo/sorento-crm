import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import IncomingContainersView from './components/IncomingContainersView';

export const metadata: Metadata = {
  title: 'Incoming Containers',
  description: 'Read the packing list, then decide what each container draws down.',
};

export default function IncomingContainersPage() {
  return (
    <RequireAccess permission="scm.reorder.run">
      <Container>
        <PageHeader title="Incoming Containers" />
      </Container>

      <Container>
        <IncomingContainersView />
      </Container>
    </RequireAccess>
  );
}
