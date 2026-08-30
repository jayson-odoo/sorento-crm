import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RespondOutboxList from './components/RespondOutboxList';

export const metadata: Metadata = {
  title: 'Respond Outbox',
  description: 'Outgoing Respond.io / WhatsApp messages and templates sent by the system.',
};

export default function RespondOutboxPage() {
  return (
    <>
      <Container>
        <PageHeader title="Respond Outbox" />
      </Container>
      <Container>
        <RespondOutboxList />
      </Container>
    </>
  );
}
