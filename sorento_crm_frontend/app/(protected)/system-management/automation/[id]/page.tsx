'use client';

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Pencil, Play } from 'lucide-react';
import { toast } from 'sonner';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Container } from '@/components/common/container';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import { Switch } from '@/components/ui/switch';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import {
  useAutomation,
  useRunAutomationNow,
  useToggleAutomation,
} from '../hooks/useAutomations';
import AutomationForm from '../components/AutomationForm';
import AutomationRunsTable from '../components/AutomationRunsTable';

export default function AutomationDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params?.id ?? '';
  const { data: automation, isLoading, refetch } = useAutomation(id || null);
  const toggleMut = useToggleAutomation(id);
  const runMut = useRunAutomationNow(id);
  const [editing, setEditing] = useState(false);

  const recipientCount =
    (automation?.recipient_config?.user_ids.length ?? 0) +
    (automation?.recipient_config?.role_ids.length ?? 0) +
    (automation?.recipient_config?.extra_emails.length ?? 0) +
    (automation?.recipient_config?.include_promotion_owner ? 1 : 0);

  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>{automation?.name ?? 'Automation'}</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href="/system-management/automation">Automation</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>{automation?.name ?? '...'}</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions>
            <Button variant="outline" size="sm" onClick={() => router.push('/system-management/automation')}>
              <ArrowLeft className="mr-1 size-4" /> Back
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!automation || runMut.isPending}
              onClick={async () => {
                try {
                  const r = await runMut.mutateAsync();
                  toast.success(`Run queued: ${r.recipients_attempted} recipient(s)`);
                } catch (err) {
                  toast.error((err as Error).message || 'Run failed');
                }
              }}
            >
              <Play className="mr-1 size-4" /> Run now
            </Button>
            <Button size="sm" onClick={() => setEditing(true)} disabled={!automation}>
              <Pencil className="mr-1 size-4" /> Edit
            </Button>
          </ToolbarActions>
        </Toolbar>
      </Container>

      <Container>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Overview</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {isLoading || !automation ? (
                <p className="text-muted-foreground">Loading…</p>
              ) : (
                <>
                  <Row label="Description" value={automation.description ?? <Empty />} />
                  <Row
                    label="Enabled"
                    value={
                      <div className="flex items-center gap-2">
                        <Switch
                          checked={automation.enabled}
                          onCheckedChange={(c) => toggleMut.mutate(c)}
                          disabled={toggleMut.isPending}
                        />
                        <Badge variant={automation.enabled ? 'success' : 'secondary'}>
                          {automation.enabled ? 'Active' : 'Disabled'}
                        </Badge>
                      </div>
                    }
                  />
                  <Row label="Last run" value={automation.last_run_at ? formatDateTimeInMalaysia(automation.last_run_at) : <Empty />} />
                  <Row label="Last status" value={automation.last_status ?? <Empty />} />
                  <Row label="Next run" value={automation.next_run_at ? formatDateTimeInMalaysia(automation.next_run_at) : <Empty />} />
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Trigger</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {automation ? (
                <>
                  <Row label="Type" value={<Badge variant="secondary">{automation.trigger_type}</Badge>} />
                  <Row
                    label="Config"
                    value={
                      <pre className="text-xs bg-muted rounded p-2 max-w-full overflow-x-auto">
                        {JSON.stringify(automation.trigger_config ?? {}, null, 2)}
                      </pre>
                    }
                  />
                </>
              ) : (
                <Empty />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Recipients ({recipientCount})</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {automation && recipientCount > 0 ? (
                <>
                  <Row label="Users" value={automation.recipient_config.user_ids.length || <Empty />} />
                  <Row label="Roles" value={automation.recipient_config.role_ids.length || <Empty />} />
                  <Row label="Promotion owner" value={automation.recipient_config.include_promotion_owner ? 'Yes' : <Empty />} />
                  <Row
                    label="External emails"
                    value={
                      automation.recipient_config.extra_emails.length ? (
                        <div className="flex flex-wrap gap-1">
                          {automation.recipient_config.extra_emails.map((e) => (
                            <Badge key={e} variant="secondary">
                              {e}
                            </Badge>
                          ))}
                        </div>
                      ) : (
                        <Empty />
                      )
                    }
                  />
                </>
              ) : (
                <Empty hint="No recipients configured. Edit the automation to add some." />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Schedule</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {automation ? (
                <>
                  <Row
                    label="Type"
                    value={
                      automation.schedule_type === 'daily' ? (
                        <Badge variant="secondary">Daily</Badge>
                      ) : (
                        <Badge variant="secondary" appearance="ghost">
                          Manual only
                        </Badge>
                      )
                    }
                  />
                  {automation.schedule_type === 'daily' && (
                    <>
                      <Row label="Run time" value={automation.run_time?.slice(0, 5) ?? <Empty />} />
                      <Row label="Timezone" value={automation.timezone} />
                    </>
                  )}
                </>
              ) : (
                <Empty />
              )}
            </CardContent>
          </Card>
        </div>

        <div className="mt-4">{automation && <AutomationRunsTable automationId={automation.id} />}</div>
      </Container>

      {automation && (
        <AutomationForm
          open={editing}
          onOpenChange={setEditing}
          automation={automation}
          onSaved={() => void refetch()}
        />
      )}
    </>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <div className="text-right">{value}</div>
    </div>
  );
}

function Empty({ hint }: { hint?: string } = {}) {
  return <span className="text-muted-foreground italic">{hint ?? '—'}</span>;
}
