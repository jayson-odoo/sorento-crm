import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { ForecastClient } from './components/ForecastClient';

export const metadata: Metadata = {
  title: 'Project Forecast & Reports',
  description:
    'Pipeline, weighted and committed value kept apart, delivery by year, conversion, loss reasons and performance by salesperson.',
};

export default function ProjectReportsPage() {
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6">
        <ForecastClient />
      </Container>
    </RequireAccess>
  );
}
