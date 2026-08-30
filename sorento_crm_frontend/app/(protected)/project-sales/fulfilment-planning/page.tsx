import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { FulfilmentPlanningClient } from './components/FulfilmentPlanningClient';

export const metadata: Metadata = {
  title: 'Fulfilment Planning',
  description:
    'Published project sales orders, whether AutoCount has been reconciled to each one, and what is still in the way.',
};

export default function FulfilmentPlanningPage() {
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6">
        <FulfilmentPlanningClient />
      </Container>
    </RequireAccess>
  );
}
