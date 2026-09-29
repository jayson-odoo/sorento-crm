import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { QuotationFormClient } from '../../components/QuotationFormClient';

export const metadata: Metadata = {
  title: 'Edit quotation',
  description:
    'The whole quotation, its letterhead, scopes and lines, in one form.',
};

/**
 * Edit quotation, from the gear on the quotation page (#1341). The same form as create, filled.
 *
 * Outside the `(view)` route group on purpose: the quotation page's layout carries the read
 * header, the tabs and the Issue CTA, and a form under it would show two headers and two CTAs.
 */
export default async function EditProjectQuotationPage({
  params,
}: {
  params: Promise<{ projectId: string; documentId: string }>;
}) {
  const { projectId, documentId } = await params;
  return (
    <RequireAccess permission="projects.projects.edit">
      <Container className="pb-64">
        <QuotationFormClient projectId={projectId} documentId={documentId} />
      </Container>
    </RequireAccess>
  );
}
