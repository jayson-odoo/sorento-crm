'use client';

import { use } from 'react';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ConversationSLATrackingDetail from '../../conversation-sla-tracking/components/ConversationSLATrackingDetail';

export default function FormSLATrackingDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  return (
    <>
      <Container>
        <PageHeader
          title="Form SLA Tracking"
          actions={
            <Button asChild variant="outline">
              <Link href="/sla-management/form-sla-tracking">
                <MoveLeft /> Back to tracking
              </Link>
            </Button>
          }
        />
      </Container>
      <Container>
        <ConversationSLATrackingDetail
          trackingId={id}
          backHref="/sla-management/form-sla-tracking"
          backLabel="Form SLA Tracking"
        />
      </Container>
    </>
  );
}
