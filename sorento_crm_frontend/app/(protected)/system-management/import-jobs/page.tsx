import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import ImportJobsList from './components/ImportJobsList';

export const metadata: Metadata = {
  title: 'Import Jobs',
  description: 'View import job status and progress.',
};

export default function ImportJobsPage() {
  return (
    <RequireAccess superadmin>
      <Container>
        <PageHeader title="Import Jobs" />
      </Container>

      <Container>
        <ImportJobsList />
      </Container>
    </RequireAccess>
  );
}
