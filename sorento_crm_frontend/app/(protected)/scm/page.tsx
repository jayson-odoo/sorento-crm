import { Metadata } from 'next';
import Link from 'next/link';
import { ClipboardList } from 'lucide-react';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Button } from '@/components/ui/button';
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
          <ToolbarActions>
            {/* M8-B6: header nav to the reorder planning page (daily cron + Manual
                plan live there now). Navigates only - no inline run. */}
            <Button asChild>
              <Link href="/scm/reorder">
                <ClipboardList className="size-4" />
                Reorder plan
              </Link>
            </Button>
          </ToolbarActions>
        </Toolbar>
      </Container>

      <Container width="fluid">
        <ScmDashboard />
      </Container>
    </>
  );
}
