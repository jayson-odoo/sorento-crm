import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import WorkflowSubmissionsList from '../../../components/WorkflowSubmissionsList';

export const metadata: Metadata = {
  title: 'Workflow submissions',
};

export default async function WorkflowSubmissionsForFormPage({
  params,
}: {
  params: Promise<{ definitionId: string }>;
}) {
  const { definitionId } = await params;
  return (
    <>
      <Container>
        <PageHeader
          title="Submissions"
          crumbs={[
            { title: 'Workflow Forms' },
            { title: 'Definitions', path: '/workflow-forms-management/definitions' },
            { title: 'Submissions' },
          ]}
        />
      </Container>
      <Container>
        <WorkflowSubmissionsList fixedDefinitionId={definitionId} />
      </Container>
    </>
  );
}
