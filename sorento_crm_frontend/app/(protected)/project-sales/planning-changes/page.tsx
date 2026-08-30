import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { PlanningChangesListClient } from './components/PlanningChangesListClient';

export const metadata: Metadata = {
  title: 'Planning Changes',
  description: 'Every re-uploaded sales order book that moved a planned line, and what was done about it.',
};

export default function PlanningChangesPage() {
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6">
        <PlanningChangesListClient />
      </Container>
    </RequireAccess>
  );
}
