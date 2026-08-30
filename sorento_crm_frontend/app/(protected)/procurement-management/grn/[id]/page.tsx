import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import GRNDetail from '../components/GRNDetail';

export const metadata: Metadata = {
  title: 'GRN Details',
  description: 'View GRN details and picking lines',
};

export default function GRNDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return (
    <Container>
      <PageHeader
        title="Goods Receipt Note"
        eyebrow="GRN"
        actions={
          <BackToList listPath="/procurement-management/grn" label="Back to GRN" />
        }
      />
      <div className="mt-6">
        <GRNDetailWrapper params={params} />
      </div>
    </Container>
  );
}

async function GRNDetailWrapper({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <GRNDetail grnId={id} />;
}
