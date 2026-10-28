import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { PipelineClient } from './components/PipelineClient';
import { PROJECT_VIEW_PERMISSIONS } from '@/app/(protected)/project-sales/_shared/projectViewPermissions';

export const metadata: Metadata = {
  title: 'Project Pipeline',
  description: 'Registered project pursuits, their stage, and who owns each one.',
};

export default function ProjectPipelinePage() {
  return (
    <RequireAccess permission={PROJECT_VIEW_PERMISSIONS}>
      <Container className="space-y-6">
        <PipelineClient />
      </Container>
    </RequireAccess>
  );
}
