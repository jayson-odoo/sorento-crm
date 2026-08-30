import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { PlansClient } from './components/PlansClient';

export const metadata: Metadata = {
  title: 'Plans',
  description: 'Every confirmed sales-order supply composition, one row per revision.',
};

export default function PlansPage() {
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6">
        <PlansClient />
      </Container>
    </RequireAccess>
  );
}
