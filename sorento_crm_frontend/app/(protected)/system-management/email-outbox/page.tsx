import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import EmailOutboxList from './components/EmailOutboxList';

export const metadata: Metadata = {
  title: 'Email Outbox',
  description: 'View and manage queued outbound emails under the email guardrail.',
};

export default function EmailOutboxPage() {
  return (
    <>
      <Container>
        <PageHeader title="Email Outbox" />
      </Container>
      <Container>
        <EmailOutboxList />
      </Container>
    </>
  );
}
