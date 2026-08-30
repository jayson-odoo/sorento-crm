import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { projectCrumbs } from '@/app/(protected)/project-sales/_shared/lib/crumbs';
import RequireAccess from '@/app/components/common/RequireAccess';
import { POIntakeConfirmClient } from '../../components/POIntakeConfirmClient';

export const metadata: Metadata = {
  title: 'Customer PO',
  description: 'What we read off an uploaded customer PO, beside the page it came from.',
};

/**
 * The confirm screen is a page, not a modal: it is file centric and side by side, which is
 * exactly the case the CRUD standard carves out.
 */
export default async function PurchaseOrderVersionPage({
  params,
}: {
  params: Promise<{ projectId: string; versionId: string }>;
}) {
  const { projectId, versionId } = await params;
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6">
        <PageHeader
          title="Purchase Order Version"
          crumbs={projectCrumbs(projectId, { title: 'Purchase Order Version' })}
        />
        <POIntakeConfirmClient projectId={projectId} versionId={versionId} />
      </Container>
    </RequireAccess>
  );
}
