import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import TeamPendingList from './components/TeamPendingList';

export const metadata: Metadata = {
  title: 'My Team Tasks',
  description: "Unresolved SLA tasks across your teams.",
};

export default async function TeamPendingPage() {
  return (
    <>
      <Container>
        <PageHeader title="My Team Tasks" />
      </Container>

      <Container>
        <TeamPendingList />
      </Container>
    </>
  );
}
