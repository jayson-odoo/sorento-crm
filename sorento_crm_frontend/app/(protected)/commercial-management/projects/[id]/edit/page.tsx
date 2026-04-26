import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import ProjectEditForm from '../../components/ProjectEditForm';

export const metadata: Metadata = {
  title: 'Edit project',
  description: 'Edit commercial project.',
};

export default async function CommercialProjectEditPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <Container width="fluid" className="bg-[#f9fafb] pb-10 pt-6">
      <ProjectEditForm projectId={id} />
    </Container>
  );
}
