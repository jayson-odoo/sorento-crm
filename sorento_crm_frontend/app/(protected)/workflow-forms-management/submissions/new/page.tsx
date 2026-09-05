import { Suspense } from 'react';
import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { NewWorkflowSubmission } from '../../components/WorkflowSubmissionEditor';

export const metadata: Metadata = {
  title: 'New workflow submission',
};

export default async function NewWorkflowSubmissionPage({
  searchParams,
}: {
  searchParams: Promise<{ definitionId?: string }>;
}) {
  const sp = await searchParams;
  return (
    <>
      <Container>
        <PageHeader
          title="New submission"
          crumbs={[
            { title: 'Workflow submissions', path: '/workflow-forms-management/submissions' },
            { title: 'New submission' },
          ]}
        />
      </Container>
      <Container>
        <Suspense fallback={<SectionSkeleton rows={5} className="p-2" />}>
          <NewWorkflowSubmission defaultDefinitionId={sp.definitionId} />
        </Suspense>
      </Container>
    </>
  );
}
