import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import ImportLogsList from './components/ImportLogsList';

export const metadata: Metadata = {
  title: 'Import Logs',
  description: 'View import history and logs.',
};

export default function ImportLogsPage() {
  return (
    <RequireAccess superadmin>
      <Container>
        <PageHeader title="Import Logs" />
      </Container>

      <Container>
        <ImportLogsList />
      </Container>
    </RequireAccess>
  );
}
