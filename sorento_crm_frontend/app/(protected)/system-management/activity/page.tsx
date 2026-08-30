import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import ActivityTimeline from './components/ActivityTimeline';

export const metadata: Metadata = {
  title: 'Activity Timeline',
  description: 'A human-readable feed of what changed across the system.',
};

export default function ActivityTimelinePage() {
  return (
    <RequireAccess superadmin>
      <Container>
        <PageHeader title="Activity Timeline" />
      </Container>

      <Container>
        <ActivityTimeline />
      </Container>
    </RequireAccess>
  );
}
