import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { WorkflowSubmissionDetail } from '../../components/WorkflowSubmissionEditor';

export const metadata: Metadata = {
  title: 'Workflow submission',
};

export default async function WorkflowSubmissionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <>
      <Container>
        <PageHeader
          title="Submission"
          // The sidebar stops at Definitions, so the list this record came from
          // has to be named here or the trail loses its only way back.
          crumbs={[
            { title: 'Workflow submissions', path: '/workflow-forms-management/submissions' },
            { title: 'Submission' },
          ]}
        />
      </Container>
      <Container>
        <WorkflowSubmissionDetail submissionId={id} />
      </Container>
    </>
  );
}
