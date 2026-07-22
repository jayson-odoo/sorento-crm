'use client';

import { Fragment, useMemo, useState } from 'react';
import Link from 'next/link';
import { format } from 'date-fns';
import { CalendarIcon, ChevronDown, ChevronRight, GitBranch, Loader2 } from 'lucide-react';
import { DateRange } from 'react-day-picker';
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from 'recharts';
import { useHasPermission } from '@/hooks/usePermissions';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Calendar } from '@/components/ui/calendar';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { ChartContainer, ChartTooltip, ChartTooltipContent } from '@/components/ui/chart';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { SearchableSelect } from '@/components/common/SearchableSelect';
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
import {
  useQueryDetail,
  useRecentQueries,
  useTopContacts,
  useTopUsers,
  useUsageByDay,
  useUsageSummary,
} from '../hooks/useAIUsage';

const FEATURE_ALL = 'all';
const FEATURE_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: FEATURE_ALL, label: 'All AI usage' },
  { value: 'ai_assistant', label: 'AI Assistant (chat)' },
  { value: 'ai_extract', label: 'AI Extract (portal forms)' },
];

const PERMISSION = 'system.ai_assistant_settings.view';

function defaultRange(): DateRange {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - 7);
  return { from, to };
}

function formatNumber(n: number | null | undefined): string {
  if (n == null) return '0';
  return n.toLocaleString();
}

function formatDateTime(d: string): string {
  try {
    return format(new Date(d), 'MMM d, HH:mm:ss');
  } catch {
    return d;
  }
}

export default function AIUsagePage() {
  const hasPermission = useHasPermission(PERMISSION);

  const [dateRange, setDateRange] = useState<DateRange | undefined>(defaultRange());
  const [pendingRange, setPendingRange] = useState<DateRange | undefined>(dateRange);
  const [datePopoverOpen, setDatePopoverOpen] = useState(false);
  const [featureFilter, setFeatureFilter] = useState<string>(FEATURE_ALL);

  const from = dateRange?.from;
  const to = dateRange?.to;
  const featureForApi = featureFilter === FEATURE_ALL ? undefined : featureFilter;

  const summaryQuery = useUsageSummary(from, to, featureForApi);
  const byDayQuery = useUsageByDay(from, to, featureForApi);
  const topUsersQuery = useTopUsers(from, to, 10, featureForApi);
  const topContactsQuery = useTopContacts(from, to, 10, featureForApi ?? 'ai_extract');
  const recentQueriesQuery = useRecentQueries(from, to, 50, featureForApi);

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const queryDetail = useQueryDetail(expandedId);

  const chartData = useMemo(() => {
    return (byDayQuery.data || []).map((d) => ({
      date: d.date,
      messages: d.messages,
      tokens: d.tokens,
    }));
  }, [byDayQuery.data]);

  const chartConfig = useMemo(
    () => ({
      tokens: { label: 'Tokens', color: 'hsl(var(--primary))' },
      messages: { label: 'Messages', color: 'hsl(var(--muted-foreground))' },
    }),
    [],
  );

  if (!hasPermission) {
    return (
      <Container>
        <div className="rounded-md border p-6 text-sm text-muted-foreground">
          Forbidden — you don&apos;t have permission to view AI assistant usage.
        </div>
      </Container>
    );
  }

  const handleRangeApply = () => {
    setDateRange(pendingRange);
    setDatePopoverOpen(false);
  };

  const handleRangeReset = () => {
    const def = defaultRange();
    setDateRange(def);
    setPendingRange(def);
    setDatePopoverOpen(false);
  };

  const summary = summaryQuery.data;

  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>AI Usage</ToolbarTitle>
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
                  <BreadcrumbPage>Usage</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
        </Toolbar>
      </Container>
      <Container className="space-y-4">
        <div className="flex items-center gap-3">
          <Popover open={datePopoverOpen} onOpenChange={setDatePopoverOpen}>
            <PopoverTrigger asChild>
              <Button
                id="usage-date"
                variant="outline"
                className={cn(
                  'w-60 justify-start font-normal',
                  !dateRange && 'text-muted-foreground',
                )}
              >
                <CalendarIcon className="h-4 w-4" />
                {dateRange?.from ? (
                  dateRange.to ? (
                    <>
                      {format(dateRange.from, 'LLL dd, y')} - {format(dateRange.to, 'LLL dd, y')}
                    </>
                  ) : (
                    format(dateRange.from, 'LLL dd, y')
                  )
                ) : (
                  <span>Filter by date range</span>
                )}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="start">
              <Calendar
                mode="range"
                defaultMonth={pendingRange?.from}
                selected={pendingRange}
                onSelect={setPendingRange}
                numberOfMonths={2}
              />
              <div className="flex items-center justify-end gap-1.5 border-t border-border p-3">
                <Button variant="outline" onClick={handleRangeReset}>
                  Reset
                </Button>
                <Button onClick={handleRangeApply}>Apply</Button>
              </div>
            </PopoverContent>
          </Popover>
          <div data-testid="ai-usage-feature-filter">
            <SearchableSelect
              value={featureFilter}
              onChange={setFeatureFilter}
              options={FEATURE_OPTIONS.map((opt) => ({ value: opt.value, label: opt.label }))}
              placeholder="All AI usage"
              triggerClassName="w-60"
            />
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-4">
          <SummaryCard
            label="Messages"
            value={formatNumber(summary?.total_messages)}
            loading={summaryQuery.isLoading}
          />
          <SummaryCard
            label="Total tokens"
            value={formatNumber(summary?.total_tokens)}
            loading={summaryQuery.isLoading}
          />
          <SummaryCard
            label="Prompt tokens"
            value={formatNumber(summary?.prompt_tokens)}
            loading={summaryQuery.isLoading}
          />
          <SummaryCard
            label="Completion tokens"
            value={formatNumber(summary?.completion_tokens)}
            loading={summaryQuery.isLoading}
          />
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Tokens per day</CardTitle>
            <CardDescription>Total tokens consumed by date</CardDescription>
          </CardHeader>
          <CardContent>
            {byDayQuery.isLoading ? (
              <div className="flex h-64 items-center justify-center text-muted-foreground">
                <Loader2 className="size-4 animate-spin" />
              </div>
            ) : chartData.length === 0 ? (
              <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
                No usage data for the selected range.
              </div>
            ) : (
              <ChartContainer config={chartConfig} className="h-64 w-full">
                <LineChart data={chartData} margin={{ left: 8, right: 8, top: 8, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Line
                    type="monotone"
                    dataKey="tokens"
                    stroke="var(--color-tokens)"
                    strokeWidth={2}
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="messages"
                    stroke="var(--color-messages)"
                    strokeWidth={1.5}
                    dot={false}
                  />
                </LineChart>
              </ChartContainer>
            )}
          </CardContent>
        </Card>

        <div className="grid gap-3 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Top users</CardTitle>
              <CardDescription>Internal staff — highest message volume in range</CardDescription>
            </CardHeader>
            <CardContent>
              {topUsersQuery.isLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  Loading...
                </div>
              ) : (topUsersQuery.data || []).length === 0 ? (
                <p className="text-sm text-muted-foreground">No user activity yet.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-xs text-muted-foreground">
                      <th className="py-2 text-left font-medium">#</th>
                      <th className="py-2 text-left font-medium">Name</th>
                      <th className="py-2 text-right font-medium">Messages</th>
                      <th className="py-2 text-right font-medium">Tokens</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(topUsersQuery.data || []).map((u, i) => (
                      <tr key={u.user_id} className="border-b last:border-0">
                        <td className="py-2 text-muted-foreground">{i + 1}</td>
                        <td className="py-2">{u.name || u.user_id}</td>
                        <td className="py-2 text-right tabular-nums">{formatNumber(u.messages)}</td>
                        <td className="py-2 text-right tabular-nums">{formatNumber(u.tokens)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Top contacts</CardTitle>
              <CardDescription>
                Portal contacts (by phone) — defaults to AI Extract spend
              </CardDescription>
            </CardHeader>
            <CardContent>
              {topContactsQuery.isLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  Loading...
                </div>
              ) : (topContactsQuery.data || []).length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No portal contact activity in range.
                </p>
              ) : (
                <table className="w-full text-sm" data-testid="ai-usage-top-contacts">
                  <thead>
                    <tr className="border-b text-xs text-muted-foreground">
                      <th className="py-2 text-left font-medium">#</th>
                      <th className="py-2 text-left font-medium">Phone</th>
                      <th className="py-2 text-left font-medium">Name</th>
                      <th className="py-2 text-right font-medium">Calls</th>
                      <th className="py-2 text-right font-medium">Tokens</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(topContactsQuery.data || []).map((c, i) => (
                      <tr key={c.contact_id} className="border-b last:border-0">
                        <td className="py-2 text-muted-foreground">{i + 1}</td>
                        <td className="py-2 font-mono text-xs">{c.phone_number || '—'}</td>
                        <td className="py-2">{c.name || <span className="text-muted-foreground italic">unknown</span>}</td>
                        <td className="py-2 text-right tabular-nums">{formatNumber(c.messages)}</td>
                        <td className="py-2 text-right tabular-nums">{formatNumber(c.tokens)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="grid gap-3 md:grid-cols-1">

          <Card>
            <CardHeader>
              <CardTitle>Recent queries</CardTitle>
              <CardDescription>Most recent assistant turns</CardDescription>
            </CardHeader>
            <CardContent>
              {recentQueriesQuery.isLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  Loading...
                </div>
              ) : (recentQueriesQuery.data || []).length === 0 ? (
                <p className="text-sm text-muted-foreground">No recent queries in range.</p>
              ) : (
                <div className="max-h-[420px] overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-background">
                      <tr className="border-b text-xs text-muted-foreground">
                        <th className="w-6 py-2"></th>
                        <th className="py-2 text-left font-medium">Time</th>
                        <th className="py-2 text-left font-medium">Feature</th>
                        <th className="py-2 text-left font-medium">Principal</th>
                        <th className="py-2 text-left font-medium">Query</th>
                        <th className="py-2 text-right font-medium">ms</th>
                        <th className="py-2 text-right font-medium">Tokens</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(recentQueriesQuery.data || []).map((q) => {
                        // message_id is null for ai_extract rows; key on a stable composite.
                        const rowKey = q.message_id ?? `${q.created_at}-${q.contact_phone ?? q.user_name ?? ''}`;
                        const isExpanded = q.message_id != null && expandedId === q.message_id;
                        const featureLabel = q.feature === 'ai_extract'
                          ? 'AI Extract'
                          : q.feature === 'ai_assistant'
                            ? 'AI Assistant'
                            : '—';
                        const principal =
                          q.contact_phone || q.contact_name
                            ? `${q.contact_name ?? 'unknown'} · ${q.contact_phone ?? ''}`.trim()
                            : q.user_name || '—';
                        return (
                          <Fragment key={rowKey}>
                            <tr
                              className={cn(
                                'border-b hover:bg-muted/40',
                                q.message_id ? 'cursor-pointer' : '',
                              )}
                              onClick={() =>
                                q.message_id &&
                                setExpandedId(isExpanded ? null : q.message_id)
                              }
                            >
                              <td className="py-2 align-top">
                                {q.message_id ? (
                                  isExpanded ? (
                                    <ChevronDown className="size-3.5 text-muted-foreground" />
                                  ) : (
                                    <ChevronRight className="size-3.5 text-muted-foreground" />
                                  )
                                ) : null}
                              </td>
                              <td className="py-2 align-top text-xs whitespace-nowrap text-muted-foreground">
                                {formatDateTime(q.created_at)}
                              </td>
                              <td className="py-2 align-top text-xs">{featureLabel}</td>
                              <td className="py-2 align-top" title={principal}>
                                {principal}
                              </td>
                              <td
                                className="max-w-[240px] truncate py-2 align-top"
                                title={q.query_preview}
                              >
                                {q.query_preview}
                              </td>
                              <td className="py-2 text-right align-top tabular-nums">
                                {formatNumber(q.response_time_ms)}
                              </td>
                              <td className="py-2 text-right align-top tabular-nums">
                                {formatNumber(q.tokens)}
                              </td>
                            </tr>
                            {isExpanded ? (
                              <tr className="border-b bg-muted/20">
                                <td></td>
                                <td colSpan={6} className="space-y-2 py-3 pe-3">
                                  {queryDetail.isLoading ? (
                                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                      <Loader2 className="size-3 animate-spin" /> Loading detail...
                                    </div>
                                  ) : queryDetail.isError ? (
                                    <p className="text-xs text-destructive">
                                      {(queryDetail.error as Error)?.message ||
                                        'Failed to load query detail.'}
                                    </p>
                                  ) : queryDetail.data ? (
                                    <>
                                      {q.feature !== 'ai_extract' && q.message_id ? (
                                        <div>
                                          <Link
                                            href={`/system-management/ai-assistant/usage/trace/${encodeURIComponent(q.message_id)}`}
                                            className="inline-flex items-center gap-1 text-xs font-medium text-primary underline underline-offset-2"
                                            data-testid="view-trace-link"
                                          >
                                            <GitBranch className="size-3" />
                                            View full trace
                                          </Link>
                                        </div>
                                      ) : null}
                                      <div>
                                        <p className="text-xs font-medium text-muted-foreground">
                                          Reply
                                        </p>
                                        <p className="mt-1 whitespace-pre-wrap text-xs">
                                          {queryDetail.data.reply || (
                                            <span className="italic text-muted-foreground">
                                              (empty reply)
                                            </span>
                                          )}
                                        </p>
                                      </div>
                                      <div>
                                        <p className="text-xs font-medium text-muted-foreground">
                                          Tools used
                                        </p>
                                        {queryDetail.data.tools_used.length === 0 ? (
                                          <p className="mt-1 text-xs italic text-muted-foreground">
                                            None
                                          </p>
                                        ) : (
                                          <ul className="mt-1 list-disc ps-4 text-xs">
                                            {queryDetail.data.tools_used.map((t, i) => (
                                              <li
                                                key={`${t.name}-${i}`}
                                                className={cn(
                                                  t.ok ? '' : 'text-destructive',
                                                )}
                                              >
                                                <span className="font-mono">{t.name}</span>{' '}
                                                {t.ok ? '' : '(failed)'}
                                              </li>
                                            ))}
                                          </ul>
                                        )}
                                      </div>
                                    </>
                                  ) : null}
                                </td>
                              </tr>
                            ) : null}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </Container>
    </>
  );
}

function SummaryCard({
  label,
  value,
  loading,
}: {
  label: string;
  value: string;
  loading: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl">
          {loading ? <Loader2 className="size-4 animate-spin" /> : value}
        </CardTitle>
      </CardHeader>
    </Card>
  );
}
