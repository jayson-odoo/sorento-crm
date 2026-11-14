import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RecordEntityRegistrar from '@/components/common/RecordEntityRegistrar';
import SampleRequestDetail from '../components/SampleRequestDetail';
import SampleRequestDetailTabs from '../components/SampleRequestDetailTabs';
import { SampleRequestPageHeader } from '../components/SampleRequestPageHeader';

export const metadata: Metadata = {
  title: 'Sample Request',
  description: 'View a sample request',
};

export default async function SampleRequestDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <Container>
      <SampleRequestPageHeader title="Sample Request" mode="back" />
      <div className="mt-6">
        <SampleRequestDetailTabs id={id}>
          <RecordEntityRegistrar entityType="sample_request" id={id} />
          <SampleRequestDetail requestId={id} />
        </SampleRequestDetailTabs>
      </div>
    </Container>
  );
}
