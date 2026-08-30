import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import EmailEventConfigsTable from './components/EmailEventConfigsTable';

export const metadata: Metadata = {
  title: 'Email Event Configs',
  description: 'Toggle and tune per-event email kill switches.',
};

export default function EmailEventConfigsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Email Event Configs" />
      </Container>
      <Container>
        <EmailEventConfigsTable />
      </Container>
    </>
  );
}
