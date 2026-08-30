import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { MyTasksClient } from './components/MyTasksClient';

export const metadata: Metadata = {
  title: 'My Project Tasks',
  description: 'Open project tasks assigned to you or escalated to you, soonest first.',
};

export default function MyProjectTasksPage() {
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6">
        <MyTasksClient />
      </Container>
    </RequireAccess>
  );
}
