import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import OutgoingMailsList from './components/OutgoingMailsList';

export const metadata: Metadata = {
  title: 'Outgoing Mails',
  description: 'View outgoing email deliveries and status.',
};

export default function OutgoingMailsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Outgoing Mails" />
      </Container>

      <Container>
        <OutgoingMailsList />
      </Container>
    </>
  );
}

