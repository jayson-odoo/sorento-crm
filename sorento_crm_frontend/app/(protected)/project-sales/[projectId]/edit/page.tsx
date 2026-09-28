import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { projectCrumbs } from '@/app/(protected)/project-sales/_shared/lib/crumbs';
import RequireAccess from '@/app/components/common/RequireAccess';
import BackToList from '@/components/common/BackToList';
import { EditProjectClient } from './components/EditProjectClient';

export const metadata: Metadata = {
  title: 'Edit project',
  description: 'Change what was registered - salesperson, lead, brands and every other field.',
};

export default async function EditProjectPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return (
    <RequireAccess permission="projects.projects.edit">
      <Container className="space-y-6">
        {/* Crumbs left, one Back right (D6, S3-01); no subtitle under the title. */}
        <PageHeader
          title="Edit project"
          crumbs={projectCrumbs(projectId, { title: 'Edit' })}
          actions={
            <BackToList listPath={`/project-sales/${projectId}`} label="Back to the project" />
          }
        />
        <EditProjectClient projectId={projectId} />
      </Container>
    </RequireAccess>
  );
}
