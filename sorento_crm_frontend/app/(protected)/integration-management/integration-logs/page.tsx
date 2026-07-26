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
import IntegrationLogsList from './components/IntegrationLogsList';

export const metadata: Metadata = {
  title: 'Integration Logs',
  description: 'View and manage integration logs.',
};

export default async function IntegrationLogsPage() {
  return (
    <RequireAccess superadmin>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Integration Logs</ToolbarTitle>
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
          <IntegrationLogsList />
        </Suspense>
      </Container>
    </RequireAccess>
  );
}
