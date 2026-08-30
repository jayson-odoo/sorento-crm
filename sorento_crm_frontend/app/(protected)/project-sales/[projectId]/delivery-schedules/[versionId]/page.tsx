import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { projectCrumbs } from '@/app/(protected)/project-sales/_shared/lib/crumbs';
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
 * front of them. It gets the full container.
 */
export default async function DeliveryScheduleReviewPage({
  params,
}: {
  params: Promise<{ projectId: string; versionId: string }>;
}) {
  const { projectId, versionId } = await params;
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6">
        <PageHeader
          title="Delivery Schedule"
          crumbs={projectCrumbs(projectId, { title: 'Delivery Schedule' })}
        />
        <DeliveryScheduleReviewClient projectId={projectId} versionId={versionId} />
      </Container>
    </RequireAccess>
  );
}
