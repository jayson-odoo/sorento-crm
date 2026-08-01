import { Metadata } from 'next';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Container } from '@/components/common/container';
import { Toolbar, ToolbarHeading, ToolbarTitle } from '@/components/common/toolbar';
import RequireAccess from '@/app/components/common/RequireAccess';
import StatusGraphsClient from './components/StatusGraphsClient';

export const metadata: Metadata = {
  title: 'Status Graphs',
  description:
    'Configure the statuses each entity can hold and the moves allowed between them.',
};

export default function StatusGraphsPage() {
  return (
    <RequireAccess permission="system.statuses.view">
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Status Graphs</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href="/system-management/import-jobs">
                    System Management
                  </BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Status Graphs</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
        </Toolbar>
      </Container>

      <Container className="space-y-6">
        <StatusGraphsClient />
      </Container>
    </RequireAccess>
  );
}
