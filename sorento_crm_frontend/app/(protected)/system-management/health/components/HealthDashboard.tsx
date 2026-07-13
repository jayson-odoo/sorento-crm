'use client';

import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useHealthSummary } from '../hooks/useHealth';
import type {
  AuditActivityHealth,
  EmailOutboxHealth,
  ImportsHealth,
  IntegrationsHealth,
  ScheduledTasksHealth,
} from '../types/health.types';

/** ISO timestamp for "24 hours ago" — used to scope integration drill-downs. */
function last24hFromIso(): string {
  return new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
}

/**
 * Build the audit-logs drill-down href for a single trend day.
 * The trend date is a UTC calendar day (YYYY-MM-DD); scope the whole UTC day.
 */
function auditDayHref(date: string): string {
  const params = new URLSearchParams({
    changed_from: `${date}T00:00:00.000Z`,
    changed_to: `${date}T23:59:59.999Z`,
  });
  return `/system-management/audit-logs?${params.toString()}`;
}

/** Build the integration-logs drill-down href for a channel's failed rows in the last 24h. */
function integrationFailedHref(channel: string): string {
  const params = new URLSearchParams({
    integration_channel: channel,
    status: 'failed',
    created_from: last24hFromIso(),
  });
  return `/integration-management/integration-logs?${params.toString()}`;
}

function MetricValue({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-2xl font-semibold text-foreground">{value}</span>
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
  );
}

function SectionEmpty({ message }: { message: string }) {
  return (
    <div className="flex min-h-20 items-center justify-center text-sm text-muted-foreground">
      {message}
    </div>
  );
}

function EmailOutboxCard({ data }: { data: EmailOutboxHealth | null }) {
  const warn = (data?.failed_last_24h ?? 0) > 0;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Email Queue</CardTitle>
        {warn && (
          <Badge variant="destructive" appearance="light" size="sm">
            {data!.failed_last_24h} failed / 24h
          </Badge>
        )}
      </CardHeader>
      <CardContent>
        {data ? (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <MetricValue label="Pending" value={data.pending} />
            <MetricValue label="Sent" value={data.sent} />
            <MetricValue label="Failed" value={data.failed} />
            <MetricValue label="Cancelled" value={data.cancelled} />
          </div>
        ) : (
          <SectionEmpty message="Email outbox not available." />
        )}
      </CardContent>
    </Card>
  );
}

function ImportsCard({ data }: { data: ImportsHealth | null }) {
  const warn = (data?.failed_last_24h ?? 0) > 0;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Imports (24h)</CardTitle>
        {data && (
          <Badge variant={warn ? 'warning' : 'success'} appearance="light" size="sm">
            {data.success_rate}% success
          </Badge>
        )}
      </CardHeader>
      <CardContent>
        {data ? (
          data.total_last_24h > 0 ? (
            <div className="grid grid-cols-3 gap-4">
              <MetricValue label="Total" value={data.total_last_24h} />
              <MetricValue label="Finished" value={data.finished_last_24h} />
              <MetricValue label="Failed" value={data.failed_last_24h} />
            </div>
          ) : (
            <SectionEmpty message="No imports in the last 24 hours." />
          )
        ) : (
          <SectionEmpty message="Import jobs not available." />
        )}
      </CardContent>
    </Card>
  );
}

function ScheduledTasksCard({ data }: { data: ScheduledTasksHealth | null }) {
  const warnOverdue = (data?.overdue ?? 0) > 0;
  const warnFailed = (data?.last_run_failed ?? 0) > 0;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Scheduled Tasks</CardTitle>
        {warnOverdue && (
          <Badge variant="warning" appearance="light" size="sm">
            {data!.overdue} overdue
          </Badge>
        )}
      </CardHeader>
      <CardContent>
        {data ? (
          <div className="grid grid-cols-3 gap-4">
            <MetricValue label="Total" value={data.total} />
            <div className="flex flex-col gap-1">
              {warnOverdue ? (
                <Link
                  href="/system-management/scheduled-tasks"
                  data-testid="health-scheduled-overdue-link"
                  className="w-fit cursor-pointer text-2xl font-semibold text-destructive underline-offset-4 hover:underline focus-visible:underline focus-visible:outline-none"
                >
                  {data.overdue}
                </Link>
              ) : (
                <span className="text-2xl font-semibold text-foreground">{data.overdue}</span>
              )}
              <span className="text-xs text-muted-foreground">Overdue</span>
            </div>
            <div className="flex flex-col gap-1">
              {warnFailed ? (
                <Link
                  href="/system-management/scheduled-tasks"
                  data-testid="health-scheduled-failed-link"
                  className="w-fit cursor-pointer text-2xl font-semibold text-destructive underline-offset-4 hover:underline focus-visible:underline focus-visible:outline-none"
                >
                  {data.last_run_failed}
                </Link>
              ) : (
                <span className="text-2xl font-semibold text-foreground">
                  {data.last_run_failed}
                </span>
              )}
              <span className="text-xs text-muted-foreground">Last run failed</span>
            </div>
          </div>
        ) : (
          <SectionEmpty message="Scheduled tasks not available." />
        )}
      </CardContent>
    </Card>
  );
}

function IntegrationsCard({ data }: { data: IntegrationsHealth | null }) {
  const channels = data?.channels ?? [];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Integrations (24h)</CardTitle>
      </CardHeader>
      <CardContent>
        {!data ? (
          <SectionEmpty message="Integration logs not available." />
        ) : channels.length === 0 ? (
          <SectionEmpty message="No integration activity in the last 24 hours." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Channel</TableHead>
                <TableHead className="text-right">Success</TableHead>
                <TableHead className="text-right">Failed</TableHead>
                <TableHead className="text-right">Total</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {channels.map((c) => (
                <TableRow key={c.channel}>
                  <TableCell className="max-w-40 truncate" title={c.channel}>
                    {c.channel}
                  </TableCell>
                  <TableCell className="text-right">{c.success}</TableCell>
                  <TableCell className="text-right">
                    {c.failed > 0 ? (
                      <Link
                        href={integrationFailedHref(c.channel)}
                        data-testid={`health-integration-failed-link-${c.channel}`}
                        className="cursor-pointer font-medium text-destructive underline-offset-2 hover:underline focus-visible:underline focus-visible:outline-none"
                        title={`View ${c.failed} failed ${c.channel} log(s) from the last 24h`}
                      >
                        {c.failed}
                      </Link>
                    ) : (
                      c.failed
                    )}
                  </TableCell>
                  <TableCell className="text-right">{c.total}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

function AuditActivityCard({ data }: { data: AuditActivityHealth | null }) {
  const trend = data?.daily_trend ?? [];
  const max = Math.max(1, ...trend.map((t) => t.count));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Audit Activity</CardTitle>
        {data && (
          <Badge variant="info" appearance="light" size="sm">
            {data.count_last_24h} / 24h
          </Badge>
        )}
      </CardHeader>
      <CardContent>
        {!data ? (
          <SectionEmpty message="Audit log not available." />
        ) : trend.length === 0 ? (
          <SectionEmpty message="No audit activity recorded." />
        ) : (
          <div className="flex items-end gap-2 pt-2" style={{ height: 96 }}>
            {trend.map((t) => (
              <Link
                key={t.date}
                href={auditDayHref(t.date)}
                data-testid={`health-audit-day-link-${t.date}`}
                aria-label={`View ${t.count} audit entries on ${t.date}`}
                title={`${t.date}: ${t.count} — view entries`}
                className="group flex flex-1 cursor-pointer flex-col items-center gap-1 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <div
                  className="w-full rounded-sm bg-primary/70 transition-colors group-hover:bg-primary group-focus-visible:bg-primary"
                  style={{ height: `${Math.round((t.count / max) * 72)}px` }}
                />
                <span className="text-[10px] text-muted-foreground group-hover:text-foreground">
                  {t.date.slice(5)}
                </span>
              </Link>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function DashboardSkeleton() {
  return (
    <div
      className="grid grid-cols-1 gap-5 lg:grid-cols-2"
      role="status"
      aria-label="Loading system health"
    >
      {Array.from({ length: 4 }).map((_, i) => (
        <Card key={i}>
          <CardHeader>
            <Skeleton className="h-5 w-32" />
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-4">
              {Array.from({ length: 3 }).map((__, j) => (
                <div key={j} className="flex flex-col gap-2">
                  <Skeleton className="h-7 w-12" />
                  <Skeleton className="h-3 w-16" />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function ErrorCard({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Unable to load system health</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col items-start gap-4">
          <p className="text-sm text-muted-foreground">{message}</p>
          <Button variant="outline" onClick={onRetry}>
            Retry
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function HealthDashboard() {
  const { data, isLoading, isError, error, refetch } = useHealthSummary();

  if (isLoading) return <DashboardSkeleton />;

  if (isError || !data) {
    return (
      <ErrorCard
        message={error instanceof Error ? error.message : 'Failed to load system health.'}
        onRetry={() => refetch()}
      />
    );
  }

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
      <EmailOutboxCard data={data.email_outbox} />
      <ImportsCard data={data.imports} />
      <ScheduledTasksCard data={data.scheduled_tasks} />
      <IntegrationsCard data={data.integrations} />
      <div className="lg:col-span-2">
        <AuditActivityCard data={data.audit_activity} />
      </div>
    </div>
  );
}
