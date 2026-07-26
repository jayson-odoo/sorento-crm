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
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import RequireAccess from '@/app/components/common/RequireAccess';
import WorkCalendarConfigCard from './components/WorkCalendarConfigCard';
import PublicHolidaysList from './components/PublicHolidaysList';

export const metadata: Metadata = {
  title: 'Work Calendar',
  description: 'Manage working days and public holidays.',
};

export default function WorkCalendarPage() {
  return (
    <RequireAccess superadmin>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Work Calendar</ToolbarTitle>
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
        </Toolbar>
      </Container>

      <Container className="space-y-6">
        <WorkCalendarConfigCard />
        <PublicHolidaysList />
      </Container>
    </RequireAccess>
  );
}
