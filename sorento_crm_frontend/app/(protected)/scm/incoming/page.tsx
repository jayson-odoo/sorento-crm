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
import IncomingContainersView from './components/IncomingContainersView';

export const metadata: Metadata = {
  title: 'Incoming Containers',
  description: 'Read the packing list, then decide what each container draws down.',
};

export default function IncomingContainersPage() {
  return (
    <RequireAccess permission="scm.reorder.run">
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Incoming Containers</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href="/scm">Supply Chain</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Incoming Containers</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions />
        </Toolbar>
      </Container>

      <Container>
        <IncomingContainersView />
      </Container>
    </RequireAccess>
  );
}
