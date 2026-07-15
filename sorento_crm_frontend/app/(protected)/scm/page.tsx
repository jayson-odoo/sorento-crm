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
import { ScmDashboard } from './components/ScmDashboard';

export const metadata: Metadata = {
  title: 'Supply Chain Dashboard',
  description: 'Net position, stock valuation and warehouse health.',
};

export default function ScmDashboardPage() {
  return (
    <>
      <Container width="fluid">
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Supply Chain</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Supply Chain</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions />
        </Toolbar>
      </Container>

      <Container width="fluid">
        <ScmDashboard />
      </Container>
    </>
  );
}
