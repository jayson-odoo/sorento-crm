import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import SalesAgentsList from './components/SalesAgentsList';

export const metadata: Metadata = {
  title: 'Sales Agents',
  description: 'The salesperson master.',
};

export default async function SalesAgentsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Sales Agents" />
      </Container>

      <Container>
        <SalesAgentsList />
      </Container>
    </>
  );
}
