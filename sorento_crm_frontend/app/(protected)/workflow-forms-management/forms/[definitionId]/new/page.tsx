import { Suspense } from 'react';
import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
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
        <PageHeader
          title="New submission"
          crumbs={[
            { title: 'Workflow Forms' },
            { title: 'Definitions', path: '/workflow-forms-management/definitions' },
            {
              title: 'Submissions',
              path: `/workflow-forms-management/forms/${definitionId}/submissions`,
            },
            { title: 'New submission' },
          ]}
        />
      </Container>
      <Container>
        <Suspense fallback={<SectionSkeleton rows={5} className="p-2" />}>
          <NewWorkflowSubmission defaultDefinitionId={definitionId} lockDefinition />
        </Suspense>
      </Container>
    </>
  );
}
