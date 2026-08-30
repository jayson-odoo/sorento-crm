import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import SPOAllocationDetail from '../components/SPOAllocationDetail';

export const metadata: Metadata = {
  title: 'SPO Allocation Details',
  description: 'View SPO allocation details',
};

export default function SPOAllocationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return (
    <Container>
      <PageHeader title="Supplier PO Allocation" eyebrow="SPO" />
      <div className="mt-6">
        <SPOAllocationDetailWrapper params={params} />
      </div>
    </Container>
  );
}

async function SPOAllocationDetailWrapper({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <SPOAllocationDetail spoAllocationId={id} />;
}
