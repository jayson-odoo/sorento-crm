import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { QuotationFormClient } from '../components/QuotationFormClient';

export const metadata: Metadata = {
  title: 'New quotation',
  description: 'The letterhead, the scopes and their lines, saved together.',
};

/**
 * Add a quotation lands here (#1341). Nothing exists until Save: the owner asked to "add product
 * straight away and save when I am satisfied", not to be dropped on a draft that was already made.
 */
export default async function NewProjectQuotationPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return (
    <RequireAccess permission="projects.projects.edit">
      <Container className="pb-64">
        <QuotationFormClient projectId={projectId} />
      </Container>
    </RequireAccess>
  );
}
