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
        <PageHeader title="Submission" />
      </Container>
      <Container>
        <WorkflowSubmissionDetail submissionId={id} />
      </Container>
    </>
  );
}
