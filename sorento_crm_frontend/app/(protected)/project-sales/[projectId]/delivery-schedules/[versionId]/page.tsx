import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { DeliveryScheduleReviewClient } from '../components/DeliveryScheduleReviewClient';

export const metadata: Metadata = {
  title: 'Delivery schedule',
  description:
    'One version of a delivery schedule, reconciled column by column against the PO.',
};

/**
 * Its own route rather than a tab panel: the matrix is as wide as the customer has products
 * (38 columns on the real documents) and the reviewer works through it against the paper in
 * front of them. It gets the full container. The client carries its own PageHeader (S5): the
 * PO number, version and status only resolve once it fetches the version, so a static header
 * here would be a second, out-of-date one stacked above it.
 */
export default async function DeliveryScheduleReviewPage({
  params,
}: {
  params: Promise<{ projectId: string; versionId: string }>;
}) {
  const { projectId, versionId } = await params;
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-4">
        <DeliveryScheduleReviewClient projectId={projectId} versionId={versionId} />
      </Container>
    </RequireAccess>
  );
}
