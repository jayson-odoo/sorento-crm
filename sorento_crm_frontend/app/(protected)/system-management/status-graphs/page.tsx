import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import StatusGraphsClient from './components/StatusGraphsClient';

export const metadata: Metadata = {
  title: 'Status Graphs',
  description:
    'Configure the statuses each entity can hold and the moves allowed between them.',
};

export default function StatusGraphsPage() {
  return (
    <RequireAccess permission="system.statuses.view">
      <Container>
        <PageHeader title="Status Graphs" />
      </Container>

      <Container className="space-y-6">
        <StatusGraphsClient />
      </Container>
    </RequireAccess>
  );
}
