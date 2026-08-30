import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';

import ComplaintResolutionDetail from './ComplaintResolutionDetail';

export const metadata: Metadata = {
  title: 'Resolution Details',
  description: 'View a complaint resolution and the complaints linked to it.',
};

export default async function ComplaintResolutionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <Container>
      <PageHeader
        title="Resolution"
        actions={<BackToList listPath="/complaint-management/complaint-resolutions" label="Back to resolutions" />}
      />
      <div className="mt-6">
        <ComplaintResolutionDetail id={id} />
      </div>
    </Container>
  );
}
