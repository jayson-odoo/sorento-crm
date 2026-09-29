import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { POIntakeConfirmClient } from '../../components/POIntakeConfirmClient';

export const metadata: Metadata = {
  title: 'Customer PO',
  description: 'What we read off an uploaded customer PO, beside the page it came from.',
};

/**
 * The review screen is a page, not a modal: it is file centric, which is exactly the case
 * the CRUD standard carves out. It carries its own PageHeader (S6): the PO number, version
 * and status only resolve once the client fetches the version, so a static header here would
 * be a second, out-of-date one stacked above it.
 */
export default async function PurchaseOrderVersionPage({
  params,
}: {
  params: Promise<{ projectId: string; versionId: string }>;
}) {
  const { projectId, versionId } = await params;
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-4">
        <POIntakeConfirmClient projectId={projectId} versionId={versionId} />
      </Container>
    </RequireAccess>
  );
}
