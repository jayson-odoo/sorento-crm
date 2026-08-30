import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';

import ComplaintRootCauseDetail from './ComplaintRootCauseDetail';

export const metadata: Metadata = {
  title: 'Root Cause Details',
  description: 'View a complaint root cause and the complaints linked to it.',
};

export default async function ComplaintRootCauseDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <Container>
      <PageHeader
        title="Root Cause"
        actions={<BackToList listPath="/complaint-management/complaint-root-causes" label="Back to root causes" />}
      />
      <div className="mt-6">
        <ComplaintRootCauseDetail id={id} />
      </div>
    </Container>
  );
}
