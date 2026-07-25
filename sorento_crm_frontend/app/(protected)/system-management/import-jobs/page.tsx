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
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
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
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Import Jobs</ToolbarTitle>
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
        <ImportJobsList />
      </Container>
    </RequireAccess>
  );
}
