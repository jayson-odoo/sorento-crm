import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { PROJECT_VIEW_PERMISSIONS } from '@/app/(protected)/project-sales/_shared/projectViewPermissions';
import { CertificateReader } from './components/CertificateReader';

export const metadata: Metadata = {
  title: 'Certificate',
  description: 'One certificate of a quotation, with the rows boxed for the customer.',
};

/**
 * Outside the quotation's `(view)` group on purpose, like the spec sheet reader: this page has its
 * own header and a document header with its tabs above would be a second one.
 */
export default async function ProjectQuotationCertificatePage({
  params,
}: {
  params: Promise<{ projectId: string; documentId: string; certificateId: string }>;
}) {
  const { projectId, documentId, certificateId } = await params;
  return (
    <RequireAccess anyPermission={PROJECT_VIEW_PERMISSIONS}>
      <Container className="pb-24">
        <CertificateReader projectId={projectId} documentId={documentId} certificateId={certificateId} />
      </Container>
    </RequireAccess>
  );
}
