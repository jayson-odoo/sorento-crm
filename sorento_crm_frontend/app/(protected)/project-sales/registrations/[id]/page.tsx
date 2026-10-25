import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import ProjectRegistrationReview from '../components/ProjectRegistrationReview';

export const metadata: Metadata = {
  title: 'Register project',
  description: 'Review a project registration',
};

export default async function ProjectRegistrationPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <RequireAccess permission="projects.registrations.approve">
      <Container className="space-y-6">
        <ProjectRegistrationReview id={id} />
      </Container>
    </RequireAccess>
  );
}
