import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import WorkflowSubmissionsList from '../components/WorkflowSubmissionsList';

export const metadata: Metadata = {
  title: 'Workflow submissions',
};

export default function WorkflowSubmissionsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Workflow submissions" />
      </Container>
      <Container>
        <WorkflowSubmissionsList />
      </Container>
    </>
  );
}
