import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { PartiesClient } from './components/PartiesClient';

export const metadata: Metadata = {
  title: 'Project Parties',
  description:
    'Developers, architects, main contractors, trading houses and consultants, reused across projects.',
};

export default function ProjectPartiesPage() {
  return (
    <RequireAccess permission="projects.parties.view">
      <Container className="space-y-6">
        <PartiesClient />
      </Container>
    </RequireAccess>
  );
}
