import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import AccessAgentsList from './components/AccessAgentsList';

export const metadata: Metadata = {
  title: 'AI Agents',
  description: 'Manage AI agents.',
};

export default async function AccessAgentsPage() {
  return (
    <>
      <Container>
        <PageHeader title="AI Agents" />
      </Container>

      <Container>
        <AccessAgentsList />
      </Container>
    </>
  );
}
