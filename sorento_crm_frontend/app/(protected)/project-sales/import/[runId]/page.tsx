import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { ProjectImportRunClient } from './components/ProjectImportRunClient';

/** One project import run (PLAN-project-import-12nov.md, AC-PI-45..48). */
export const metadata = { title: 'Project import' };

export default async function Page({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return (
    <RequireAccess permission="projects.import.view">
      <Container>
        <ProjectImportRunClient runId={runId} />
      </Container>
    </RequireAccess>
  );
}
