import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
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
        <PageHeader title="Work Calendar" />
      </Container>

      <Container className="space-y-6">
        <WorkCalendarConfigCard />
        <PublicHolidaysList />
      </Container>
    </RequireAccess>
  );
}
