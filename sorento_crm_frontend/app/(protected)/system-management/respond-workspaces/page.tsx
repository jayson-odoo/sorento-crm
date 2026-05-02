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
import RespondWorkspacesAdmin from './components/RespondWorkspacesAdmin';

export const metadata: Metadata = {
  title: 'Respond.io Workspaces',
  description: 'Manage Respond.io workspaces (name, space ID, API key, base URL, default).',
};

export default function Page() {
  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Respond.io Workspaces</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href="/system-management/app-store">System Management</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Respond.io Workspaces</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
        </Toolbar>
      </Container>
      <Container>
        <RespondWorkspacesAdmin />
      </Container>
    </>
  );
}
