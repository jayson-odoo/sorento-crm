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
  return (
    <RequireAccess permission="projects.projects.edit">
      <Container className="pb-24">
        <SpecSheetPageEditor
          projectId={projectId}
          documentId={documentId}
          sheetId={sheetId}
          pageKey={key}
        />
      </Container>
    </RequireAccess>
  );
}
