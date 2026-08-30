import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import WorkflowDefinitionsList from '../components/WorkflowDefinitionsList';

export const metadata: Metadata = {
  title: 'Workflow form definitions',
  description: 'Build approval-style forms.',
};

export default function WorkflowDefinitionsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Workflow form definitions" />
      </Container>
      <Container>
        <WorkflowDefinitionsList />
      </Container>
    </>
  );
}
