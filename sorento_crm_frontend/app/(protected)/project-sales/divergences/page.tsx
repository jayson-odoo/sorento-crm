import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { DivergenceListClient } from './components/DivergenceListClient';

export const metadata: Metadata = {
  title: 'AutoCount Differences',
  description:
    'Sales orders where AutoCount no longer agrees with what we published, and how long each has waited.',
};

export default function ProjectDivergencesPage() {
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6">
        <DivergenceListClient />
      </Container>
    </RequireAccess>
  );
}
