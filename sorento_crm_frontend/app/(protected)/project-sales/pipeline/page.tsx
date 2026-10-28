import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { PipelineClient } from './components/PipelineClient';

export const metadata: Metadata = {
  title: 'Project Pipeline',
  description: 'Registered project pursuits, their stage, and who owns each one.',
};

const PROJECT_VIEW_PERMISSIONS = ['projects.projects.view', 'projects.projects.view_own'];

export default function ProjectPipelinePage() {
  return (
    <RequireAccess permission={PROJECT_VIEW_PERMISSIONS}>
      <Container className="space-y-6">
        <PipelineClient />
      </Container>
    </RequireAccess>
  );
}
