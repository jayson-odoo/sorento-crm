import { Suspense } from 'react';
import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { NewWorkflowSubmission } from '../../../components/WorkflowSubmissionEditor';

export const metadata: Metadata = {
  title: 'New workflow submission',
};

export default async function NewWorkflowSubmissionForFormPage({
  params,
}: {
  params: Promise<{ definitionId: string }>;
}) {
  const { definitionId } = await params;
  return (
    <>
      <Container>
        <PageHeader title="New submission" />
      </Container>
      <Container>
        <Suspense fallback={<p className="text-muted-foreground p-2">Loading…</p>}>
          <NewWorkflowSubmission defaultDefinitionId={definitionId} lockDefinition />
        </Suspense>
      </Container>
    </>
  );
}
