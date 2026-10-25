import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import ProjectRegistrationsList from './components/ProjectRegistrationsList';

export const metadata: Metadata = {
  title: 'Registrations',
  description: 'Project registrations from the portal',
};

export default function ProjectRegistrationsPage() {
  return (
    <RequireAccess permission="projects.registrations.approve">
      <Container>
        <PageHeader title="Registrations" />
      </Container>

      <Container>
        <ProjectRegistrationsList />
      </Container>
    </RequireAccess>
  );
}
