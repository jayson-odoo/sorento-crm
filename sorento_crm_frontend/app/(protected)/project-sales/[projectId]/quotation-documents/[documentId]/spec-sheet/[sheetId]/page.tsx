import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { PROJECT_VIEW_PERMISSIONS } from '@/app/(protected)/project-sales/_shared/projectViewPermissions';
import { SpecSheetReader } from './components/SpecSheetReader';

export const metadata: Metadata = {
  title: 'Spec sheet',
  description: 'The pages of one spec sheet, read like a PDF.',
};

/**
 * Outside the quotation's `(view)` group on purpose: the reader has its own header (the sheet, its
 * revision, Export PDF) and a document header with its tabs above would be a second one.
 */
export default async function ProjectQuotationSpecSheetReaderPage({
  params,
}: {
  params: Promise<{ projectId: string; documentId: string; sheetId: string }>;
}) {
  const { projectId, documentId, sheetId } = await params;
  return (
    <RequireAccess anyPermission={PROJECT_VIEW_PERMISSIONS}>
      <Container className="pb-24">
        <SpecSheetReader projectId={projectId} documentId={documentId} sheetId={sheetId} />
      </Container>
    </RequireAccess>
  );
}
