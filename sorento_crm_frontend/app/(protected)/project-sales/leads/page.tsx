import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { LeadsClient } from './components/LeadsClient';

export const metadata: Metadata = {
  title: 'Leads',
  description:
    'Developments we have heard about but nobody has claimed yet. Qualifying one registers it.',
};

export default function ProjectLeadsPage() {
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6">
        <LeadsClient />
      </Container>
    </RequireAccess>
  );
}
