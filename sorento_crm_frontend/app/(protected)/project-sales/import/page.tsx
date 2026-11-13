import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import { ProjectImportListClient } from './components/ProjectImportListClient';

/** Project import runs (PLAN-project-import-12nov.md, AC-PI-42/43). */
export const metadata = { title: 'Project import' };

export default function Page() {
  return (
    <RequireAccess permission="projects.import.view">
      <Container>
        <PageHeader title="Project import" />
      </Container>
      <Container>
        <ProjectImportListClient />
      </Container>
    </RequireAccess>
  );
}
