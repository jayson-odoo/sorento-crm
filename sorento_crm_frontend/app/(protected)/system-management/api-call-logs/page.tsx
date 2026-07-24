'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  type ColumnDef,
  type PaginationState,
  type SortingState,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Search, X } from 'lucide-react';
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
import { Card, CardFooter, CardTable } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Container } from '@/components/common/container';
import { Toolbar, ToolbarHeading, ToolbarTitle } from '@/components/common/toolbar';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { getApiCallLogs, getApiCallLogSources } from './services/apiCallLogService';
import { ApiCallDetailDrawer } from './components/ApiCallDetailDrawer';
import type { ApiCallLogRow } from './types/apiCallLog.types';

function localInput(offsetHours: number): string {
  const d = new Date(Date.now() - offsetHours * 3600_000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const OUTCOME_OPTIONS = [
  { value: '', label: 'All outcomes' },
  { value: 'success', label: 'Success' },
  { value: 'client_error', label: 'Client error (4xx)' },
  { value: 'server_error', label: 'Server error (5xx)' },
];

function OutcomeCell({ row }: { row: ApiCallLogRow }) {
  const variant =
    row.outcome === 'success' ? 'success' : row.outcome === 'client_error' ? 'warning' : 'destructive';
  return (
    <Badge variant={variant} appearance="light" size="sm">
      {row.status_code ?? '—'}
    </Badge>
  );
}

export default function ApiCallLogsPage() {
  const [dateFrom, setDateFrom] = useState(() => localInput(24));
  const [dateTo, setDateTo] = useState(() => localInput(0));
  const [source, setSource] = useState('');
  const [outcome, setOutcome] = useState('');
  const [correlationId, setCorrelationId] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [selected, setSelected] = useState<ApiCallLogRow | null>(null);

  const filters = useMemo(
    () => ({
      date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
      date_to: dateTo ? new Date(dateTo).toISOString() : undefined,
      source: source || undefined,
      outcome: outcome || undefined,
      correlation_id: correlationId || undefined,
      search: searchQuery || undefined,
      page: pagination.pageIndex + 1,
      limit: pagination.pageSize,
      sort: sorting[0]?.id,
      dir: (sorting[0]?.desc ? 'desc' : 'asc') as 'asc' | 'desc',
    }),
    [dateFrom, dateTo, source, outcome, correlationId, searchQuery, pagination, sorting],
  );

  const { data, isLoading } = useQuery({
    queryKey: ['apiCallLogs', filters],
    queryFn: () => getApiCallLogs(filters),
  });

  // Live values, so a caller that starts sending a new X-Source appears in the
  // filter the first time it calls rather than after a code change.
  const { data: sources = [] } = useQuery({
    queryKey: ['apiCallLogSources'],
    queryFn: getApiCallLogSources,
  });

  const sourceOptions = useMemo(
    () => [{ value: '', label: 'All sources' }, ...sources.map((s) => ({ value: s, label: s }))],
    [sources],
  );

  const columns = useMemo<ColumnDef<ApiCallLogRow>[]>(
    () => [
      {
        accessorKey: 'created_at',
        header: ({ column }) => <DataGridColumnHeader title="When" column={column} />,
        cell: ({ row }) => formatDateTimeInMalaysia(row.original.created_at),
        size: 170,
        meta: { headerTitle: 'When' },
      },
      {
        accessorKey: 'source',
        header: ({ column }) => <DataGridColumnHeader title="Source" column={column} />,
        cell: ({ row }) => (
          <Badge variant="secondary" appearance="ghost">
            {row.original.source}
          </Badge>
        ),
        size: 100,
        meta: { headerTitle: 'Source' },
      },
      {
        accessorKey: 'method',
        header: ({ column }) => <DataGridColumnHeader title="Method" column={column} />,
        cell: ({ row }) => <span className="font-mono text-xs">{row.original.method}</span>,
        size: 80,
        meta: { headerTitle: 'Method' },
      },
      {
        accessorKey: 'endpoint',
        header: ({ column }) => <DataGridColumnHeader title="Endpoint" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate font-mono text-xs" title={row.original.endpoint}>
            {row.original.endpoint}
          </span>
        ),
        size: 320,
        meta: { headerTitle: 'Endpoint' },
      },
      {
        accessorKey: 'tool_name',
        header: ({ column }) => <DataGridColumnHeader title="MCP tool" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate text-xs" title={row.original.tool_name ?? ''}>
            {row.original.tool_name ?? '—'}
          </span>
        ),
        size: 150,
        meta: { headerTitle: 'MCP tool' },
      },
      {
        accessorKey: 'status_code',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => <OutcomeCell row={row.original} />,
        size: 90,
        meta: { headerTitle: 'Status' },
      },
      {
        accessorKey: 'latency_ms',
        header: ({ column }) => <DataGridColumnHeader title="Latency" column={column} />,
        cell: ({ row }) =>
          row.original.latency_ms === null ? '—' : `${row.original.latency_ms} ms`,
        size: 100,
        meta: { headerTitle: 'Latency' },
      },
    ],
    [],
  );

  const rows = data?.data ?? [];
  const total = data?.total ?? 0;

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil(total / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    manualPagination: true,
    manualSorting: true,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
  });

  return (
    <Container>
      <Toolbar>
        <ToolbarHeading>
          <ToolbarTitle>API Call Log</ToolbarTitle>
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink href="/">Home</BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>System Management</BreadcrumbPage>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>API Call Log</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </ToolbarHeading>
      </Toolbar>

      <Card className="mb-5">
        <div className="flex flex-wrap items-end gap-3 p-5">
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">From</Label>
            <Input
              type="datetime-local"
              value={dateFrom}
              data-testid="api-call-log-from"
              onChange={(e) => setDateFrom(e.target.value)}
              className="w-56"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">To</Label>
            <Input
              type="datetime-local"
              value={dateTo}
              data-testid="api-call-log-to"
              onChange={(e) => setDateTo(e.target.value)}
              className="w-56"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Source</Label>
            <SearchableSelect
              value={source}
              onChange={setSource}
              options={sourceOptions}
              placeholder="All sources"
              className="w-44"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Outcome</Label>
            <SearchableSelect
              value={outcome}
              onChange={setOutcome}
              options={OUTCOME_OPTIONS}
              placeholder="All outcomes"
              className="w-48"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Correlation id</Label>
            <Input
              value={correlationId}
              data-testid="api-call-log-correlation"
              onChange={(e) => setCorrelationId(e.target.value)}
              placeholder="Join an MCP client span"
              className="w-56"
            />
          </div>
        </div>
      </Card>

      <DataGrid
        table={table}
        recordCount={total}
        isLoading={isLoading}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        onRowClick={(row) => setSelected(row)}
      >
        <Card>
          <DataGridListToolbar
            table={table}
            searchSlot={
              <div className="relative w-full max-w-xs">
                <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search endpoint, tool, error..."
                  value={searchQuery}
                  data-testid="api-call-log-search"
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="ps-9"
                />
                {searchQuery && (
                  <Button
                    mode="icon"
                    variant="dim"
                    className="absolute end-1.5 top-1/2 h-6 w-6 -translate-y-1/2"
                    onClick={() => setSearchQuery('')}
                  >
                    <X />
                  </Button>
                )}
              </div>
            }
          />
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

      <ApiCallDetailDrawer row={selected} onClose={() => setSelected(null)} />
    </Container>
  );
}
