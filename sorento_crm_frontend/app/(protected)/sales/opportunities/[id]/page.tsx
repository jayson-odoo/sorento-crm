import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import SalesOpportunityDetail from './components/SalesOpportunityDetail';

export const metadata: Metadata = {
  title: 'Sales Opportunity',
  description: 'A possible sale being worked on.',
};

export default async function SalesOpportunityPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <>
      <Container>
        <PageHeader
          title="Sales Opportunity"
          actions={<BackToList listPath="/sales/opportunities" label="Back to opportunities" />}
        />
      </Container>
      <Container>
        <SalesOpportunityDetail id={id} />
      </Container>
    </>
  );
}
