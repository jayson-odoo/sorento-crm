import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import LoadingPlansGrid from './components/LoadingPlansGrid';

export const metadata: Metadata = {
  title: 'Loading Plan',
  description: 'Every container plan, newest first.',
};

export default function LoadingPlanPage() {
  return (
    <RequireAccess permission="scm.reorder.run">
      <Container>
        <PageHeader title="Loading Plan" />
      </Container>

      <Container>
        <LoadingPlansGrid />
      </Container>
    </RequireAccess>
  );
}
