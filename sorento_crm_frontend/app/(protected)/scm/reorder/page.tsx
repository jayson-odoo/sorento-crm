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
import { ReorderPlanningView } from './components/ReorderPlanningView';

export const metadata: Metadata = {
  title: 'Reorder Planning',
  description: 'Run reorder planning and review buy + disposition recommendations.',
};

export default async function ReorderPlanningPage({
  searchParams,
}: {
  searchParams: Promise<{ run?: string }>;
}) {
  // `?run=1` auto-opens the Manual plan modal (deep-link support; the dashboard's
  // header "Reorder plan" button now navigates here without it - M8-B6).
  const { run } = await searchParams;
  const autoOpenRun = run === '1';

  return (
    <RequireAccess permission="scm.reorder.run">
      <Container width="fluid">
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Reorder Planning</ToolbarTitle>
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
                  <BreadcrumbPage>Reorder Planning</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions />
        </Toolbar>
      </Container>

      <Container width="fluid">
        <ReorderPlanningView autoOpenRun={autoOpenRun} />
      </Container>
    </RequireAccess>
  );
}
