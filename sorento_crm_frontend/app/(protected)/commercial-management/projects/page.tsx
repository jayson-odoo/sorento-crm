import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import ProjectsList from './components/ProjectsList';

export const metadata: Metadata = {
  title: 'Projects',
  description: 'Commercial projects.',
};

export default async function CommercialProjectsPage() {
  return (
    <Container className="bg-[#f9fafb] pb-10 pt-6">
      <ProjectsList />
    </Container>
  );
}
