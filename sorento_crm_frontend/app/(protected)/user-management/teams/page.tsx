import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import TeamList from './components/team-list';

export const metadata: Metadata = {
  title: 'Teams',
  description: 'Manage teams for round-robin assignees.',
};

export default function TeamsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Teams" />
      </Container>
      <Container>
        <TeamList />
      </Container>
    </>
  );
}
