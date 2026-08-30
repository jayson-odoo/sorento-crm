import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { ProjectSetupClient } from './components/ProjectSetupClient';

export const metadata: Metadata = {
  title: 'Project Setup',
  description:
    'Project types, their templates, the stakeholder roles each template offers, and the checklist a new project starts with.',
};

export default function ProjectSetupPage() {
  return (
    <RequireAccess permission="projects.types.view">
      <Container className="space-y-6">
        <ProjectSetupClient />
      </Container>
    </RequireAccess>
  );
}
