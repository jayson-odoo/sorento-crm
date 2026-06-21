'use client';

import { type MouseEvent, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { X } from 'lucide-react';
import { formatDateTime, parseDateTimeAsUTC } from '@/lib/helpers';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from 'recharts';
import { Card, CardContent, CardHeader, CardTable, CardTitle, CardFooter } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from '@/components/ui/chart';
import { useHasPermission } from '@/hooks/usePermissions';
import {
  getKpiSummary,
  getKpiTrend,
  getKpiTasks,
  type KpiScope,
  type KpiView,
  type KpiState,
  type KpiTaskRow,
} from './slaKpiService';

// Mirrors MyPendingSLAWidget's ENTITY_ROUTES so this list navigates identically.
const ENTITY_ROUTES: Record<string, string> = {
  stock_inquiry: '/procurement-management/stock-inquiries',
  complaint: '/complaint-management/complaints',
  purchase_request: '/procurement-management/purchase-requests',
  sponsorship_form: '/procurement-management/purchase-requests',
};

function taskHref(t: KpiTaskRow): string {
  const base = ENTITY_ROUTES[t.source_entity_type ?? ''];
  if (base && t.source_entity_id) return `${base}/${t.source_entity_id}`;
  return `/sla-management/conversation-sla-tracking/${t.tracking_id}`;
}

const fmtPct = (v: number | null) => (v == null ? '—' : `${v}%`);
const fmtHrs = (v: number | null) => (v == null ? '—' : `${v}h`);
const fmtDate = (v: string | null) => (v ? formatDateTime(parseDateTimeAsUTC(v)) : '—');

type TaskFilter = { view: KpiView; state: KpiState };

const activeRing = (on: boolean) =>
  on ? 'ring-2 ring-primary ring-offset-1 ring-offset-background' : 'hover:ring-1 hover:ring-border';

function TimelinessCard({
  label, total, within, overdue, pctWithin, view, filter, onSelect,
}: {
  label: string; total: number; within: number; overdue: number; pctWithin: number | null;
  view: KpiView; filter: TaskFilter; onSelect: (f: TaskFilter) => void;
}) {
  const wPct = total > 0 ? (100 * within) / total : 0;
  const oPct = total > 0 ? (100 * overdue) / total : 0;
  const isView = filter.view === view;
  const withinActive = isView && filter.state === 'within';
  const overdueActive = isView && filter.state === 'overdue';
  const seg = (state: KpiState) => (e: MouseEvent) => { e.stopPropagation(); onSelect({ view, state }); };
  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={() => onSelect({ view, state: 'all' })}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect({ view, state: 'all' }); } }}
      className={`cursor-pointer transition ${activeRing(isView)}`}
    >
      <CardContent className="py-4">
        <div className="flex items-baseline justify-between">
          <span className="text-sm text-muted-foreground truncate" title={label}>{label}</span>
          <span className="text-sm text-muted-foreground">{total} total</span>
        </div>
        <div className="mt-1 text-2xl font-semibold">{fmtPct(pctWithin)} <span className="text-sm font-normal text-muted-foreground">within due</span></div>
        <div className="mt-3 flex h-2 w-full overflow-hidden rounded-full bg-muted">
          <button type="button" aria-label={`${label} within due`} onClick={seg('within')}
            className={`h-full bg-emerald-500 ${withinActive ? 'ring-2 ring-emerald-700' : ''}`} style={{ width: `${wPct}%` }} />
          <button type="button" aria-label={`${label} overdue`} onClick={seg('overdue')}
            className={`h-full bg-rose-500 ${overdueActive ? 'ring-2 ring-rose-700' : ''}`} style={{ width: `${oPct}%` }} />
        </div>
        <div className="mt-2 flex items-center justify-between text-xs">
          <button type="button" onClick={seg('within')}
            className={`flex items-center gap-1.5 ${withinActive ? 'font-semibold text-foreground' : 'text-muted-foreground'}`}>
            <span className="size-2 rounded-full bg-emerald-500" /> Within due {within}
          </button>
          <button type="button" onClick={seg('overdue')}
            className={`flex items-center gap-1.5 ${overdueActive ? 'font-semibold text-foreground' : 'text-muted-foreground'}`}>
            <span className="size-2 rounded-full bg-rose-500" /> Overdue {overdue}
          </button>
        </div>
      </CardContent>
    </Card>
  );
}

function StageCard({
  label, count, pct, total, accent, view, filter, onSelect,
}: {
  label: string; count: number; pct: number | null; total: number; accent: string;
  view: KpiView; filter: TaskFilter; onSelect: (f: TaskFilter) => void;
}) {
  const width = pct == null ? 0 : Math.min(100, pct);
  const isView = filter.view === view;
  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={() => onSelect({ view, state: 'all' })}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect({ view, state: 'all' }); } }}
      className={`cursor-pointer transition ${activeRing(isView)}`}
    >
      <CardContent className="py-4">
        <div className="flex items-center gap-2">
          <span className={`size-2 rounded-full ${accent}`} />
          <span className="text-sm text-muted-foreground truncate" title={label}>{label}</span>
        </div>
        <div className="mt-1 flex items-baseline gap-2">
          <span className="text-3xl font-semibold">{fmtPct(pct)}</span>
          <span className="text-sm text-muted-foreground">{count} of {total}</span>
        </div>
        <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div className={`h-full ${accent}`} style={{ width: `${width}%` }} />
        </div>
      </CardContent>
    </Card>
  );
}

const TREND_CONFIG: ChartConfig = {
  opened: { label: 'Opened', color: 'var(--primary)' },
  resolved: { label: 'Resolved', color: 'var(--muted-foreground)' },
};

function TrendCard({ scope }: { scope: KpiScope }) {
  const trendQ = useQuery({ queryKey: ['kpi-trend', scope], queryFn: () => getKpiTrend(scope) });
  return (
    <Card>
      <CardHeader className="py-4"><CardTitle className="text-base">Opened vs resolved trend</CardTitle></CardHeader>
      {/* min-w-0 lets recharts' ResponsiveContainer measure the available width
          instead of bootstrapping a min-width (works together with min-w-0 on the
          layout content column). */}
      <CardContent className="min-w-0 py-2">
        {trendQ.isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : (trendQ.data?.length ?? 0) === 0 ? (
          <div className="py-4 text-sm text-muted-foreground">No trend data for this scope.</div>
        ) : (
          <ChartContainer config={TREND_CONFIG} className="h-64 w-full min-w-0">
            <LineChart data={trendQ.data} margin={{ left: 8, right: 8, top: 8, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="bucket" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Line type="monotone" dataKey="opened" stroke="var(--color-opened)" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="resolved" stroke="var(--color-resolved)" strokeWidth={1.5} dot={false} />
            </LineChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  );
}

const VIEW_LABEL: Record<KpiView, string> = {
  all: 'All SLA tasks',
  responded: 'Responded',
  resolved: 'Resolved',
  pending: 'Awaiting response',
  responded_open: 'Responded, awaiting resolution',
};
const STATE_LABEL: Record<KpiState, string> = { all: '', within: 'within due', overdue: 'overdue' };

function filterLabel(f: TaskFilter): string {
  if (f.view === 'all') return 'All SLA tasks';
  return STATE_LABEL[f.state] ? `${VIEW_LABEL[f.view]} · ${STATE_LABEL[f.state]}` : VIEW_LABEL[f.view];
}

function TasksCard({ scope, filter, onClear }: { scope: KpiScope; filter: TaskFilter; onClear: () => void }) {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const cardRef = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const isFiltered = filter.view !== 'all';

  // Reset to first page whenever the card-driven filter changes, and bring the
  // table into view so the drilldown result is visible after a click.
  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
    if (isFiltered) cardRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  }, [filter.view, filter.state, isFiltered]);

  const tasksQ = useQuery({
    queryKey: ['kpi-tasks', scope, filter.view, filter.state, pagination.pageIndex, pagination.pageSize, sorting],
    queryFn: () => getKpiTasks(scope, pagination, sorting, filter.view, filter.state),
  });

  const data = tasksQ.data?.data ?? [];
  const total = tasksQ.data?.total ?? 0;

  const columns = useMemo<ColumnDef<KpiTaskRow>[]>(
    () => [
      {
        accessorKey: 'source_entity_type',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        cell: ({ row }) => (row.original.source_entity_type || 'conversation').replace(/_/g, ' '),
        size: 150,
      },
      {
        accessorKey: 'current_tier',
        header: ({ column }) => <DataGridColumnHeader title="Tier" column={column} />,
        size: 80,
      },
      {
        accessorKey: 'assignee_name',
        header: ({ column }) => <DataGridColumnHeader title="Owner" column={column} />,
        cell: ({ row }) => (
          <span className="truncate block" title={row.original.assignee_name}>{row.original.assignee_name}</span>
        ),
        size: 180,
      },
      {
        accessorKey: 'current_tier_started_at',
        header: ({ column }) => <DataGridColumnHeader title="Tier started" column={column} />,
        cell: ({ row }) => {
          const v = fmtDate(row.original.current_tier_started_at);
          return <span className="truncate block" title={v}>{v}</span>;
        },
        size: 160,
      },
      {
        accessorKey: 'response_due',
        header: ({ column }) => <DataGridColumnHeader title="Response due" column={column} />,
        cell: ({ row }) => {
          const v = fmtDate(row.original.response_due);
          return <span className="truncate block" title={v}>{v}</span>;
        },
        size: 160,
      },
      {
        accessorKey: 'resolution_due',
        header: ({ column }) => <DataGridColumnHeader title="Resolution due" column={column} />,
        cell: ({ row }) => {
          const v = fmtDate(row.original.resolution_due);
          return <span className="truncate block" title={v}>{v}</span>;
        },
        size: 160,
      },
      {
        accessorKey: 'response_time_hours',
        header: ({ column }) => <DataGridColumnHeader title="Resp" column={column} />,
        cell: ({ row }) => fmtHrs(row.original.response_time_hours),
        size: 90,
      },
      {
        accessorKey: 'resolution_time_hours',
        header: ({ column }) => <DataGridColumnHeader title="Reso" column={column} />,
        cell: ({ row }) => fmtHrs(row.original.resolution_time_hours),
        size: 90,
      },
      {
        id: 'escalations',
        header: 'Esc (m/a)',
        cell: ({ row }) => `${row.original.escalations_manual}/${row.original.escalations_auto}`,
        size: 100,
      },
      {
        accessorKey: 'response_met',
        header: ({ column }) => <DataGridColumnHeader title="Resp met" column={column} />,
        cell: ({ row }) => (row.original.response_met ? '✓' : '—'),
        size: 100,
      },
      {
        accessorKey: 'resolution_met',
        header: ({ column }) => <DataGridColumnHeader title="Reso met" column={column} />,
        cell: ({ row }) => (row.original.resolution_met ? '✓' : '—'),
        size: 100,
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data,
    pageCount: Math.ceil(total / pagination.pageSize),
    getRowId: (row) => row.tracking_id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  return (
    <div ref={cardRef}>
    <DataGrid
      table={table}
      recordCount={total}
      isLoading={tasksQ.isLoading}
      standardToolbar={false}
      listingKey="sla.kpi.view::tasks"
      emptyMessage="No tasks in this scope."
      onRowClick={(row) => router.push(taskHref(row))}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
    >
      <Card>
        <CardHeader className="flex flex-col gap-2 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <CardTitle className="text-base">Tasks</CardTitle>
            {isFiltered ? (
              <Badge variant="secondary" className="font-normal">{filterLabel(filter)}</Badge>
            ) : (
              <span className="text-xs text-muted-foreground">Click a card or bar segment above to filter</span>
            )}
          </div>
          {isFiltered ? (
            <Button variant="outline" size="sm" className="h-8 shrink-0" onClick={onClear}>
              <X className="size-3.5" /> Clear filter
            </Button>
          ) : null}
        </CardHeader>
        <CardTable>
          <ScrollArea>
            <DataGridTable />
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>
    </DataGrid>
    </div>
  );
}

// Body of the KPI dashboard WITHOUT the outer <Container>, so it can be embedded
// both on its own route (/sla-management/kpi-dashboard) and on the home dashboard
// (app/(protected)/page.tsx) under "My pending tasks".
export function SLAKpiDashboardContent() {
  const [scope, setScope] = useState<KpiScope>('all');
  const [filter, setFilter] = useState<TaskFilter>({ view: 'all', state: 'all' });
  const canView = useHasPermission('sla.kpi.view');

  // Toggle off when re-clicking the exact same slice; otherwise apply it.
  const selectFilter = (f: TaskFilter) =>
    setFilter((cur) => (cur.view === f.view && cur.state === f.state ? { view: 'all', state: 'all' } : f));
  const clearFilter = () => setFilter({ view: 'all', state: 'all' });

  const summaryQ = useQuery({
    queryKey: ['kpi-summary', scope],
    queryFn: () => getKpiSummary(scope),
    enabled: canView,
  });
  const s = summaryQ.data;

  if (!canView) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          You don&apos;t have access to the SLA KPI dashboard.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h1 className="text-xl font-semibold min-w-0 break-words">SLA KPI Dashboard</h1>
          <Select value={scope} onValueChange={(v) => { setScope(v as KpiScope); clearFilter(); }}>
            <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All SLA</SelectItem>
              <SelectItem value="form">Form SLA</SelectItem>
              <SelectItem value="conversation">Conversation SLA</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Stage breakdown — MECE partition of the total (sums to Opened) */}
        {summaryQ.isLoading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-28 w-full" />)}
          </div>
        ) : s ? (
          <div className="space-y-2">
            <div className="flex items-baseline justify-between">
              <h2 className="text-sm font-medium text-muted-foreground">Stage breakdown</h2>
              <span className="text-sm text-muted-foreground">{s.opened} total</span>
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <StageCard label="Awaiting response" count={s.stage_pending} pct={s.pct_stage_pending} total={s.opened} accent="bg-amber-500" view="pending" filter={filter} onSelect={selectFilter} />
              <StageCard label="Responded, awaiting resolution" count={s.stage_responded_open} pct={s.pct_stage_responded_open} total={s.opened} accent="bg-blue-500" view="responded_open" filter={filter} onSelect={selectFilter} />
              <StageCard label="Resolved" count={s.stage_resolved} pct={s.pct_stage_resolved} total={s.opened} accent="bg-emerald-500" view="resolved" filter={filter} onSelect={selectFilter} />
            </div>
          </div>
        ) : null}

        {/* Timeliness drilldown — within due vs overdue, scoped to each subset */}
        {s ? (
          <div className="space-y-2">
            <h2 className="text-sm font-medium text-muted-foreground">Timeliness drilldown (within due vs overdue)</h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <TimelinessCard
                label="Responded"
                total={s.responded}
                within={s.responded_within}
                overdue={s.responded_overdue}
                pctWithin={s.pct_responded_within}
                view="responded"
                filter={filter}
                onSelect={selectFilter}
              />
              <TimelinessCard
                label="Resolved"
                total={s.resolved}
                within={s.resolved_within}
                overdue={s.resolved_overdue}
                pctWithin={s.pct_resolved_within}
                view="resolved"
                filter={filter}
                onSelect={selectFilter}
              />
            </div>
          </div>
        ) : null}

        {/* Open work at-risk — within live clock vs overdue-but-unfinished */}
        {s ? (
          <div className="space-y-2">
            <h2 className="text-sm font-medium text-muted-foreground">Open work at risk (within due vs overdue)</h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <TimelinessCard
                label="Awaiting response"
                total={s.stage_pending}
                within={s.pending_within}
                overdue={s.pending_overdue}
                pctWithin={s.pct_pending_within}
                view="pending"
                filter={filter}
                onSelect={selectFilter}
              />
              <TimelinessCard
                label="Responded, awaiting resolution"
                total={s.stage_responded_open}
                within={s.responded_open_within}
                overdue={s.responded_open_overdue}
                pctWithin={s.pct_responded_open_within}
                view="responded_open"
                filter={filter}
                onSelect={selectFilter}
              />
            </div>
          </div>
        ) : null}

      {/* Per-task drill-down — sits right under the cards; driven by card/segment clicks */}
      <TasksCard scope={scope} filter={filter} onClear={clearFilter} />

      {/* Trend */}
      <TrendCard scope={scope} />
    </div>
  );
}
