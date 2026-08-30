'use client';

import { use } from 'react';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import ConversationSLATrackingDetail from '../components/ConversationSLATrackingDetail';

export default function ConversationSLATrackingDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  return (
    <>
      <Container>
        <PageHeader
          title="Conversation SLA Tracking"
          actions={
            <BackToList
              listPath="/sla-management/conversation-sla-tracking"
              label="Back to conversation SLA"
            />
          }
        />
      </Container>
      <Container>
        <ConversationSLATrackingDetail trackingId={id} />
      </Container>
    </>
  );
}
