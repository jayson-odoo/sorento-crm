import { Metadata } from 'next';
import { Suspense } from 'react';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import IntegrationLogsList from './components/IntegrationLogsList';

export const metadata: Metadata = {
  title: 'Integration Logs',
  description: 'View and manage integration logs.',
};

export default async function IntegrationLogsPage() {
  return (
    <RequireAccess superadmin>
      <Container>
        <PageHeader title="Integration Logs" />
      </Container>

      <Container>
        <Suspense fallback={null}>
          <IntegrationLogsList />
        </Suspense>
      </Container>
    </RequireAccess>
  );
}
