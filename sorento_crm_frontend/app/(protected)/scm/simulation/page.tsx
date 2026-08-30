import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import { SimulationView } from './components/SimulationView';

export const metadata: Metadata = {
  title: 'Engine Simulation',
  description: 'Run the reorder engine over the frozen scenario set and compare against the blessed baseline.',
};

export default function EngineSimulationPage() {
  return (
    <RequireAccess permission="scm.reorder.run">
      <Container width="fluid">
        <PageHeader title="Engine Simulation" />
      </Container>

      <Container width="fluid">
        <SimulationView />
      </Container>
    </RequireAccess>
  );
}
