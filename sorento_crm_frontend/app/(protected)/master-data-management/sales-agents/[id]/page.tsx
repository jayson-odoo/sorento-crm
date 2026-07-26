'use client';

import { use } from 'react';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Container } from '@/components/common/container';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import { AutoCountSourceBadge } from '@/components/common/AutoCountSourceBadge';
import { MirrorAnnotationCard } from '@/components/common/MirrorAnnotationCard';
import { useSalesAgent, useAnnotateSalesAgent } from '../hooks/useSalesAgents';
import { formatDate } from '@/lib/helpers';

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="font-medium">{value ?? '-'}</p>
    </div>
  );
}

function Header() {
  return (
    <Container>
      <Toolbar>
        <ToolbarHeading>
          <ToolbarTitle>Sales Agent</ToolbarTitle>
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink href="/">Home</BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>Master Data</BreadcrumbPage>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbLink href="/master-data-management/sales-agents">
                  Sales Agents
                </BreadcrumbLink>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </ToolbarHeading>
        <ToolbarActions>
          <Button asChild variant="outline">
            <Link href="/master-data-management/sales-agents">
              <MoveLeft /> Back to Sales Agents
            </Link>
          </Button>
        </ToolbarActions>
      </Toolbar>
    </Container>
  );
}

export default function SalesAgentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data: agent, isLoading } = useSalesAgent(id);
  const annotate = useAnnotateSalesAgent();

  if (isLoading) {
    return (
      <>
        <Header />
        <Container>
          <div className="space-y-6">
            <Skeleton className="h-10 w-64" />
            <Skeleton className="h-96 w-full" />
          </div>
        </Container>
      </>
    );
  }

  if (!agent) {
    return (
      <>
        <Header />
        <Container>
          <div className="text-center py-12">
            <p className="text-muted-foreground">Sales agent not found</p>
            <Button asChild variant="outline" className="mt-4">
              <Link href="/master-data-management/sales-agents">
                <MoveLeft className="size-4" /> Back to Sales Agents
              </Link>
            </Button>
          </div>
        </Container>
      </>
    );
  }

  return (
    <>
      <Header />
      <Container>
        <div className="space-y-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 space-y-1">
              <h1 className="text-2xl font-bold break-words">{agent.sales_agent}</h1>
              <p className="text-sm text-muted-foreground">Sales agent</p>
            </div>
            <AutoCountSourceBadge source={agent.source} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Basic information — always rendered */}
            <Card>
              <CardHeader>
                <CardTitle>Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <Field label="Name" value={agent.sales_agent} />
                <Field label="Description" value={agent.description || '-'} />
                <Field
                  label="Status"
                  value={
                    <Badge
                      variant={agent.is_active ? 'success' : 'secondary'}
                      appearance="ghost"
                    >
                      <BadgeDot />
                      {agent.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  }
                />
                <Field label="Created" value={formatDate(new Date(agent.created_at))} />
                {agent.updated_at && (
                  <Field label="Last Updated" value={formatDate(new Date(agent.updated_at))} />
                )}
              </CardContent>
            </Card>

            {/* Annotation — the only editable surface */}
            <MirrorAnnotationCard
              value={{ internal_note: agent.internal_note, follow_up: agent.follow_up }}
              isSaving={annotate.isPending}
              onSave={(next) => annotate.mutate({ id, data: next })}
            />
          </div>
        </div>
      </Container>
    </>
  );
}
