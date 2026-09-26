import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import { SalesTeamDetail } from './components/SalesTeamDetail';

export const metadata: Metadata = {
  title: 'Sales Team',
  description: 'A sales team and its agents.',
};

export default async function SalesTeamPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <>
      <Container>
        <PageHeader
          title="Sales Team"
          actions={<BackToList listPath="/sales/teams" label="Back to sales teams" />}
        />
      </Container>
      <Container>
        <SalesTeamDetail id={id} />
      </Container>
    </>
  );
}
