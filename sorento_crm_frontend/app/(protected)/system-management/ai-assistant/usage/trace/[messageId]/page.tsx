'use client';

import { use } from 'react';
import { useHasPermission } from '@/hooks/usePermissions';
import { Container } from '@/components/common/container';
import { Toolbar, ToolbarHeading, ToolbarTitle } from '@/components/common/toolbar';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
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
          Forbidden — you don&apos;t have permission to view AI assistant traces.
        </div>
      </Container>
    );
  }

  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Turn trace</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href="/system-management/ai-assistant">AI Assistant</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href="/system-management/ai-assistant/usage">Usage</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Trace</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
        </Toolbar>
      </Container>
      <Container className="pb-8">
        <TraceView messageId={messageId} />
      </Container>
    </>
  );
}
