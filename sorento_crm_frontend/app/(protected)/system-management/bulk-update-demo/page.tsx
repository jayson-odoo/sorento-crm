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
import BulkUpdateDemoList from './components/BulkUpdateDemoList';

export const metadata: Metadata = {
  title: 'Bulk Update (demo)',
};

export default function BulkUpdateDemoPage() {
  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Bulk Update (demo)</ToolbarTitle>
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
        <div className="mb-4 rounded-md border border-dashed bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
          Phase-1 demo — mock data. Select rows, then <span className="font-medium">Action ▾ →
          Bulk update…</span> to edit one whitelisted field across the selection.
        </div>
        <BulkUpdateDemoList />
      </Container>
    </>
  );
}
