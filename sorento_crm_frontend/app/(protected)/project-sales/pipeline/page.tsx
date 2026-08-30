import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { PipelineClient } from './components/PipelineClient';

export const metadata: Metadata = {
  title: 'Project Pipeline',
  description: 'Registered project pursuits, their stage, and who owns each one.',
};

export default function ProjectPipelinePage() {
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6">
        <PipelineClient />
      </Container>
    </RequireAccess>
  );
}
