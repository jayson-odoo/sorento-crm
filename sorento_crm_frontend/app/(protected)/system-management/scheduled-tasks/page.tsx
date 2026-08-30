import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import ScheduledTasksList from './components/ScheduledTasksList';

export const metadata: Metadata = {
  title: 'Scheduled Tasks',
  description: 'View and manage scheduled tasks.',
};

export default function ScheduledTasksPage() {
  return (
    <RequireAccess superadmin>
      <Container>
        <PageHeader title="Scheduled Tasks" />
      </Container>

      <Container>
        <ScheduledTasksList />
      </Container>
    </RequireAccess>
  );
}
