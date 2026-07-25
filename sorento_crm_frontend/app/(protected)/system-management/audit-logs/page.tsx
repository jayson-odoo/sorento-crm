import { Metadata } from 'next';
import { Suspense } from 'react';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Container } from '@/components/common/container';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
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
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Audit Logs</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>System Management</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions></ToolbarActions>
        </Toolbar>
      </Container>

      <Container>
        <Suspense fallback={null}>
          <AuditLogsList />
        </Suspense>
      </Container>
    </RequireAccess>
  );
}
