import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
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
      {/* "SPO" is never spelled out as "Supplier PO" in the UI, so the title
          carries the abbreviation and there is no eyebrow to expand it. */}
      <PageHeader
        title="SPO Allocation"
        actions={
          <BackToList
            listPath="/procurement-management/spo-allocations"
            label="Back to SPO allocations"
          />
        }
      />
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
