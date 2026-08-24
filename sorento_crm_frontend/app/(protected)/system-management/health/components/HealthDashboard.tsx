'use client';

import { Fragment, useMemo, useState } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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
  FailureSignature,
  EmailOutboxHealth,
  ImportsHealth,
  IntegrationsHealth,
  ScheduledTasksHealth,
} from '../types/health.types';

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

/**
 * Build the integration-logs drill-down href for a channel's failed rows.
 *
 * The window MUST be the one the dashboard is currently showing - this used to
 * hardcode "last 24h", so widening the picker to 30d produced a link that
 * landed on a different (smaller) set of rows than the count you clicked.
 */
function integrationFailedHref(
  channel: string,
  range: { date_from?: string; date_to?: string },
): string {
  const params = new URLSearchParams({
    integration_channel: channel,
    status: 'failed',
  });
  if (range.date_from) params.set('created_from', range.date_from);
  if (range.date_to) params.set('created_to', range.date_to);
  return `/integration-management/integration-logs?${params.toString()}`;
}

/**
 * Drill-down for ONE cause rather than a whole channel.
 *
 * Narrowed by `status_code` and `filter_terms` on top of the channel filter - 
 * a channel mixes several faults, so channel+status alone would land on all of
 * them. `filter_terms` is used rather than the sample message because the sample
 * embeds a record id that differs per row; every term is sent and the backend
 * ANDs them, because one term alone cannot separate two faults sharing a prefix.
 */
function failureCauseHref(
  channel: string,
  failure: FailureSignature,
  range: { date_from?: string; date_to?: string },
): string {
  const params = new URLSearchParams({
    integration_channel: channel,
    status: 'failed',
  });
  if (range.date_from) params.set('created_from', range.date_from);
  if (range.date_to) params.set('created_to', range.date_to);
  if (failure.status_code !== null) params.set('status_code', String(failure.status_code));
  for (const term of failure.filter_terms ?? []) params.append('error_contains', term);
  return `/integration-management/integration-logs?${params.toString()}`;
}

function MetricValue({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  /** Secondary line, e.g. the all-time figure behind a windowed number. */
  hint?: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-2xl font-semibold text-foreground">{value}</span>
      <span className="text-xs text-muted-foreground">{label}</span>
      {hint && <span className="text-[11px] text-muted-foreground/80">{hint}</span>}
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
            <MetricValue label="Pending" value={data.pending} hint="as of now" />
            <MetricValue label="Sent" value={data.sent} hint="all time" />
            <MetricValue
              label="Failed in window"
              value={data.failed_in_window ?? data.failed_last_24h}
              hint={`${data.failed} all time`}
            />
            <MetricValue label="Cancelled" value={data.cancelled} hint="all time" />
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
        {data && data.total_last_24h === 0 ? (
          // A 0% success rate over an empty window reads as a failure. It isn't:
          // nothing ran.
          <Badge variant="secondary" appearance="light" size="sm">
            No activity
          </Badge>
        ) : data ? (
          <Badge variant={warn ? 'warning' : 'success'} appearance="light" size="sm">
            {data.success_rate}% success
          </Badge>
        ) : null}
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

function IntegrationsCard({
  data,
  range,
}: {
  data: IntegrationsHealth | null;
  /** The window the dashboard is showing, so drill-downs match the counts. */
  range: { date_from?: string; date_to?: string };
}) {
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
                <TableHead className="text-right" title="Logged as a failure but expected - e.g. an idempotency race">
                  Benign
                </TableHead>
                <TableHead className="text-right" title="Still in progress (pending/processing)">
                  In flight
                </TableHead>
                <TableHead className="text-right">Total</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {channels.map((c) => (
                <Fragment key={c.channel}>
                  <TableRow className={c.top_failures?.length ? 'border-b-0' : undefined}>
                    <TableCell className="max-w-40 truncate" title={c.channel}>
                      {c.channel}
                    </TableCell>
                    <TableCell className="text-right">{c.success}</TableCell>
                    <TableCell className="text-right">
                      {c.failed > 0 ? (
                        <Link
                          href={integrationFailedHref(c.channel, range)}
                          data-testid={`health-integration-failed-link-${c.channel}`}
                          className="cursor-pointer font-medium text-destructive underline-offset-2 hover:underline focus-visible:underline focus-visible:outline-none"
                          title={`View ${c.failed} failed ${c.channel} log(s) in the selected window`}
                        >
                          {c.failed}
                        </Link>
                      ) : (
                        c.failed
                      )}
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground">
                      {c.benign > 0 ? (
                        <span title="Expected outcome logged as a failure - not an incident">
                          {c.benign}
                        </span>
                      ) : (
                        c.benign
                      )}
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground">{c.in_flight}</TableCell>
                    <TableCell className="text-right">{c.total}</TableCell>
                  </TableRow>
                  {/* The causes, inline. A count tells you something broke; this
                      tells you what, without a round-trip to the logs page. */}
                  {(c.top_failures ?? []).length > 0 && (
                    <TableRow className="hover:bg-transparent">
                      <TableCell colSpan={6} className="pt-0">
                        <ul
                          className="space-y-1 pl-2"
                          data-testid={`health-integration-failures-${c.channel}`}
                        >
                          {c.top_failures.map((f) => (
                            <li key={`${f.status_code ?? 'none'}:${f.signature}`}>
                              <Link
                                href={failureCauseHref(c.channel, f, range)}
                                data-testid={`health-integration-failure-link-${c.channel}-${f.status_code ?? 'none'}`}
                                title={`View the ${f.count} log(s) for this cause\n\n${f.sample_message}`}
                                className="flex items-start gap-2 rounded px-1 py-0.5 text-xs text-muted-foreground hover:bg-muted focus-visible:bg-muted focus-visible:outline-none"
                              >
                                <Badge variant="destructive" appearance="light" size="sm">
                                  {f.count}×
                                </Badge>
                                {f.status_code !== null && (
                                  <Badge variant="secondary" appearance="light" size="sm">
                                    {f.status_code}
                                  </Badge>
                                )}
                                <span className="min-w-0 flex-1 truncate underline-offset-2 hover:underline">
                                  {f.sample_message}
                                </span>
                              </Link>
                            </li>
                          ))}
                        </ul>
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
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
                title={`${t.date}: ${t.count} - view entries`}
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

/** `datetime-local` value for "now minus N hours", in the browser's own zone. */
function localInput(offsetHours: number): string {
  const d = new Date(Date.now() - offsetHours * 3600_000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const RANGE_PRESETS: { label: string; hours: number }[] = [
  { label: '24h', hours: 24 },
  { label: '7d', hours: 24 * 7 },
  { label: '30d', hours: 24 * 30 },
];

export default function HealthDashboard() {
  const [dateFrom, setDateFrom] = useState(() => localInput(24));
  const [dateTo, setDateTo] = useState(() => localInput(0));

  const range = useMemo(
    () => ({
      date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
      date_to: dateTo ? new Date(dateTo).toISOString() : undefined,
    }),
    [dateFrom, dateTo],
  );

  const { data, isLoading, isError, error, refetch } = useHealthSummary(range);

  const rangeBar = (
    <Card className="mb-5">
      <CardContent className="flex flex-wrap items-end gap-3 pt-6">
        <div className="space-y-1">
          <span className="text-xs text-muted-foreground">From</span>
          <Input
            type="datetime-local"
            value={dateFrom}
            data-testid="health-range-from"
            onChange={(e) => setDateFrom(e.target.value)}
            className="w-56"
          />
        </div>
        <div className="space-y-1">
          <span className="text-xs text-muted-foreground">To</span>
          <Input
            type="datetime-local"
            value={dateTo}
            data-testid="health-range-to"
            onChange={(e) => setDateTo(e.target.value)}
            className="w-56"
          />
        </div>
        <div className="flex gap-1">
          {RANGE_PRESETS.map((p) => (
            <Button
              key={p.label}
              variant="outline"
              size="sm"
              onClick={() => {
                setDateFrom(localInput(p.hours));
                setDateTo(localInput(0));
              }}
            >
              {p.label}
            </Button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground basis-full">
          Filters records by when they were created. Backlog figures (Pending, task
          counts) are always as of now - a range cannot apply to a live queue.
        </p>
      </CardContent>
    </Card>
  );

  if (isLoading)
    return (
      <>
        {rangeBar}
        <DashboardSkeleton />
      </>
    );

  if (isError || !data) {
    return (
      <>
        {rangeBar}
        <ErrorCard
          message={error instanceof Error ? error.message : 'Failed to load system health.'}
          onRetry={() => refetch()}
        />
      </>
    );
  }

  return (
    <>
    {rangeBar}
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
      <EmailOutboxCard data={data.email_outbox} />
      <ImportsCard data={data.imports} />
      <ScheduledTasksCard data={data.scheduled_tasks} />
      <div className="lg:col-span-2">
        <IntegrationsCard data={data.integrations} range={range} />
      </div>
      <div className="lg:col-span-2">
        <AuditActivityCard data={data.audit_activity} />
      </div>
    </div>
    </>
  );
}
