import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import LogList from './components/log-list';

export const metadata: Metadata = {
  title: 'Logs',
  description: 'Logs',
};

export default async function ActivityLogsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Logs" />
      </Container>

      <Container>
        <LogList />
      </Container>
    </>
  );
}
