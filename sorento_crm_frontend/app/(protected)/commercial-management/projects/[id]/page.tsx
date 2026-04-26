import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import ProjectDetail from '../components/ProjectDetail';

export const metadata: Metadata = {
  title: 'Project',
  description: 'Commercial project detail.',
};

export default async function CommercialProjectDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <Container width="fluid" className="bg-[#f9fafb] pb-10 pt-6">
      <ProjectDetail projectId={id} />
    </Container>
  );
}
