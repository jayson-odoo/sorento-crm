import { Metadata } from 'next';
import { Suspense } from 'react';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import AuditLogsList from './components/AuditLogsList';

export const metadata: Metadata = {
  title: 'Audit Logs',
  description: 'Review who changed what across the system.',
};

export default function AuditLogsPage() {
  return (
    <RequireAccess superadmin>
      <Container>
        <PageHeader title="Audit Logs" />
      </Container>

      <Container>
        <Suspense fallback={null}>
          <AuditLogsList />
        </Suspense>
      </Container>
    </RequireAccess>
  );
}
