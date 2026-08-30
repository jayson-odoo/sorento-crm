'use client';

import { use } from 'react';
import { useHasPermission } from '@/hooks/usePermissions';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { TraceView } from '../../../components/TraceView';

const PERMISSION = 'system.ai_assistant_settings.view';

export default function TracePage({
  params,
}: {
  params: Promise<{ messageId: string }>;
}) {
  const { messageId } = use(params);
  const hasPermission = useHasPermission(PERMISSION);

  if (!hasPermission) {
    return (
      <Container>
        <div className="rounded-md border p-6 text-sm text-muted-foreground">
          Forbidden - you don&apos;t have permission to view AI assistant traces.
        </div>
      </Container>
    );
  }

  return (
    <>
      <Container>
        <PageHeader title="Turn trace" />
      </Container>
      <Container className="pb-8">
        <TraceView messageId={messageId} />
      </Container>
    </>
  );
}
