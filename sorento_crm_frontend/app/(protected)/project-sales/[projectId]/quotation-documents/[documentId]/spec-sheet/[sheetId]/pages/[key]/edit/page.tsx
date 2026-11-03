import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { SpecSheetPageEditor } from '../../../components/SpecSheetPageEditor';

export const metadata: Metadata = {
  title: 'Edit spec sheet page',
  description: 'One page of a spec sheet in the tag designer.',
};

export default async function EditProjectQuotationSpecSheetPage({
  params,
}: {
  params: Promise<{ projectId: string; documentId: string; sheetId: string; key: string }>;
}) {
  const { projectId, documentId, sheetId, key } = await params;
  // The reader links with encodeURIComponent(page.key) and a server page receives the segment
  // still encoded; decode it once so the service's own encoding does not double it.
  let pageKey = key;
  try {
    pageKey = decodeURIComponent(key);
  } catch {
    // A malformed escape is left as is; the API answers it with a 404.
  }
  return (
    <RequireAccess permission="projects.projects.edit">
      <Container className="pb-24">
        <SpecSheetPageEditor
          projectId={projectId}
          documentId={documentId}
          sheetId={sheetId}
          pageKey={pageKey}
        />
      </Container>
    </RequireAccess>
  );
}
