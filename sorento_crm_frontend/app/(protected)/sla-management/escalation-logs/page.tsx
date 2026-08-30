import EventLogList from './components/EventLogList';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';

export default function EscalationLogsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Event Logs" />
      </Container>

      <Container>
        <EventLogList />
      </Container>
    </>
  );
}
