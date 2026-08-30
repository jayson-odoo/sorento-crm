import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import HealthDashboard from './components/HealthDashboard';

export const metadata: Metadata = {
  title: 'System Health',
  description: 'Operational health at a glance.',
};

export default function SystemHealthPage() {
  return (
    <RequireAccess superadmin>
      <Container>
        <PageHeader title="System Health" />
      </Container>

      <Container>
        <HealthDashboard />
      </Container>
    </RequireAccess>
  );
}
