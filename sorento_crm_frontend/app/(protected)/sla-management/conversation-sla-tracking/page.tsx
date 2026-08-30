import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ConversationSLATrackingList from './components/ConversationSLATrackingList';

export const metadata: Metadata = {
  title: 'Conversation SLA Tracking',
  description: 'View conversation SLA tracking and responsiveness metrics.',
};

export default async function ConversationSLATrackingPage() {
  return (
    <>
      <Container>
        <PageHeader title="Conversation SLA Tracking" />
      </Container>

      <Container>
        <ConversationSLATrackingList />
      </Container>
    </>
  );
}
