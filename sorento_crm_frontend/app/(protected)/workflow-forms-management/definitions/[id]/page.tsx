import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import WorkflowFormBuilder from '../../components/WorkflowFormBuilder';

export const metadata: Metadata = {
  title: 'Edit workflow form',
};

export default async function WorkflowDefinitionBuilderPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <>
      <Container>
        <PageHeader title="Edit workflow form" />
      </Container>
      <Container>
        <WorkflowFormBuilder definitionId={id} />
      </Container>
    </>
  );
}
