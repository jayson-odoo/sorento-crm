import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import SampleRequestForm from '../components/SampleRequestForm';
import { SampleRequestPageHeader } from '../components/SampleRequestPageHeader';

export const metadata: Metadata = {
  title: 'New Sample Request',
  description: 'Create a sample request',
};

export default async function NewSampleRequestPage({
  searchParams,
}: {
  searchParams: Promise<{ project_id?: string }>;
}) {
  const { project_id } = await searchParams;
  return (
    <Container>
      <SampleRequestPageHeader title="New Sample Request" mode="cancel" />
      <div className="mt-6">
        <SampleRequestForm projectId={project_id} />
      </div>
    </Container>
  );
}
