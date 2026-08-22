import { Metadata } from 'next';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
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
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink href="/">Home</BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbLink href="/project-sales/pipeline">Project Sales</BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbLink href={`/project-sales/${projectId}?tab=schedules`}>
                Delivery schedules
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Review</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <DeliveryScheduleReviewClient projectId={projectId} versionId={versionId} />
      </Container>
    </RequireAccess>
  );
}
