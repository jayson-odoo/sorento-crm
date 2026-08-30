import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import { SalesAgentDetail } from './components/SalesAgentDetail';

export const metadata: Metadata = {
  title: 'Sales Agent',
  description: 'Sales agent detail - annotations and the orders sold under this code.',
};

export default async function SalesAgentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <>
      <Container>
        <PageHeader
          title="Sales Agent"
          actions={
            <BackToList
              listPath="/master-data-management/sales-agents"
              label="Back to sales agents"
            />
          }
        />
      </Container>

      <Container>
        <SalesAgentDetail id={id} />
      </Container>
    </>
  );
}
