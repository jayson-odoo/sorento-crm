'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Search, X, ChevronRight, RefreshCw } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useIntegrationLogs, useRetryIntegrationLog } from '../hooks/useIntegrationLogs';
import type { IntegrationLog } from '../types/integrationLog.types';
import { formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { formatDateTimeInMalaysia, parseDateTimeAsUTC } from '@/lib/helpers';
import { getStatusBadgeVariant } from '@/lib/status-badge';

export default function IntegrationLogsList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [channelFilter, setChannelFilter] = useState<string>('all');
  const [tableFilter, setTableFilter] = useState<string>('all');

  const { data, isLoading, refetch, isRefetching } = useIntegrationLogs({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    status: statusFilter !== 'all' ? statusFilter : undefined,
    integration_channel: channelFilter !== 'all' ? channelFilter : undefined,
    business_table: tableFilter !== 'all' ? tableFilter : undefined,
  });

  const retryMutation = useRetryIntegrationLog();

  const columns = useMemo<ColumnDef<IntegrationLog>[]>(
    () => [
      {
        accessorKey: 'integration_channel',
        header: ({ column }) => <DataGridColumnHeader title="Channel" column={column} />,
        cell: ({ row }) => (
          <Badge variant="secondary" appearance="ghost">
            {row.original.integration_channel}
          </Badge>
        ),
        size: 120,
        meta: { skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'business_table',
        header: ({ column }) => <DataGridColumnHeader title="Business Table" column={column} />,
        cell: ({ row }) => row.original.business_table,
        size: 150,
      },
      {
        accessorKey: 'business_id',
        header: ({ column }) => <DataGridColumnHeader title="Business ID" column={column} />,
        cell: ({ row }) => (
          <span className="font-mono text-xs">{row.original.business_id.substring(0, 8)}...</span>
        ),
        size: 120,
      },
      {
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => {
          const status = (row.original.status || 'pending') as string;
          return (
            <Badge
              variant={getStatusBadgeVariant(status)}
              appearance="ghost"
              className="capitalize"
            >
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </Badge>
          );
        },
        size: 120,
      },
      {
        accessorKey: 'retry_count',
        header: ({ column }) => <DataGridColumnHeader title="Retries" column={column} />,
        cell: ({ row }) => `${row.original.retry_count}/${row.original.max_retry_allowed}`,
        size: 100,
      },
      {
        accessorKey: 'created_at',
        header: ({ column }) => <DataGridColumnHeader title="Created" column={column} />,
        cell: ({ row }) => {
          const utcDate = parseDateTimeAsUTC(row.original.created_at);
          const malaysiaTime = formatDateTimeInMalaysia(row.original.created_at);
          const relative = formatDistanceToNow(utcDate, { addSuffix: true });
          return (
            <span title={relative}>
              {malaysiaTime}
            </span>
          );
        },
        size: 180,
      },
      {
        accessorKey: 'processed_at',
        header: ({ column }) => <DataGridColumnHeader title="Processed" column={column} />,
        cell: ({ row }) => {
          if (!row.original.processed_at) return '-';
          const malaysiaTime = formatDateTimeInMalaysia(row.original.processed_at);
          return malaysiaTime;
        },
        size: 180,
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            {row.original.status === 'failed' && row.original.retry_count < row.original.max_retry_allowed && (
              <Button
                mode="icon"
                variant="ghost"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation();
                  retryMutation.mutate(row.original.id, {
                    onSuccess: () => {
                      toast.success('Retry initiated');
                      refetch();
                    },
                    onError: (error: Error) => {
                      toast.error(error.message || 'Failed to retry');
                    },
                  });
                }}
                disabled={retryMutation.isPending}
              >
                <RefreshCw className="size-4" />
              </Button>
            )}
            <ChevronRight className="text-muted-foreground/70 size-3.5" />
          </div>
        ),
        size: 80,
      },
    ],
    [retryMutation, refetch],
  );

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
  });

  return (
    <DataGrid 
      table={table} 
      recordCount={data?.pagination.total || 0} 
      isLoading={isLoading}
      onRowClick={(row) => {
        router.push(`/integration-management/integration-logs/${row.id}`);
      }}
    >
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2 flex-1">
            <div className="relative flex-1 max-w-xs">
              <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
              <Input
                placeholder="Search logs..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="ps-9"
              />
              {searchQuery && (
                <Button
                  mode="icon"
                  variant="dim"
                  className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                  onClick={() => setSearchQuery('')}
                >
                  <X />
                </Button>
              )}
            </div>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-40">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Status</SelectItem>
                <SelectItem value="pending">Pending</SelectItem>
                <SelectItem value="processing">Processing</SelectItem>
                <SelectItem value="success">Success</SelectItem>
                <SelectItem value="failed">Failed</SelectItem>
              </SelectContent>
            </Select>
            <Select value={channelFilter} onValueChange={setChannelFilter}>
              <SelectTrigger className="w-40">
                <SelectValue placeholder="Channel" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Channels</SelectItem>
                <SelectItem value="n8n">n8n</SelectItem>
                <SelectItem value="sla_management">SLA Management</SelectItem>
                <SelectItem value="sla_tracking_creation">SLA Tracking (create)</SelectItem>
                <SelectItem value="sla_tracking_update">SLA Tracking (update)</SelectItem>
                <SelectItem value="sla_escalation">SLA Escalation</SelectItem>
              </SelectContent>
            </Select>
            <Select value={tableFilter} onValueChange={setTableFilter}>
              <SelectTrigger className="w-40">
                <SelectValue placeholder="Table" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Tables</SelectItem>
                <SelectItem value="attachments">Attachments</SelectItem>
                <SelectItem value="conversation_sla_tracking">Conversation SLA Tracking</SelectItem>
                <SelectItem value="conversation_sla_event_log">Conversation SLA Event Log</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isRefetching}
            className="shrink-0"
          >
            <RefreshCw className={`size-4 mr-2 ${isRefetching ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
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
  );
}
