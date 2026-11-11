'use client';

import AccessDenied from '@/app/components/common/AccessDenied';
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
        <AccessDenied description="Only people whose role includes AI assistant settings can open this. Ask an administrator if you need it." />
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
