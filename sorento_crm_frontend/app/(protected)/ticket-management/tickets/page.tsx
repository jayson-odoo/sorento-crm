import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import TicketsList from './components/TicketsList';

export const metadata: Metadata = {
  title: 'Tickets',
  description: 'Internal Jira-style ticketing for staff issues.',
};

export default function TicketsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Tickets" />
      </Container>

      <Container>
        <TicketsList />
      </Container>
    </>
  );
}
