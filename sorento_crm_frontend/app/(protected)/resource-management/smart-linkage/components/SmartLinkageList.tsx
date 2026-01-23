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
import { useIntegrationLogs, useRetryIntegrationLog } from '@/app/(protected)/integration-management/integration-logs/hooks/useIntegrationLogs';
import type { IntegrationLog } from '@/app/(protected)/integration-management/integration-logs/types/integrationLog.types';
import { formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';

export default function SmartLinkageList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [channelFilter, setChannelFilter] = useState<string>('all');

  // Always filter by business_table = 'attachments'
  const { data, isLoading, refetch } = useIntegrationLogs({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    status: statusFilter !== 'all' ? statusFilter : undefined,
    integration_channel: channelFilter !== 'all' ? channelFilter : undefined,
    business_table: 'attachments', // Always filter by attachments
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
        accessorKey: 'business_id',
        header: ({ column }) => <DataGridColumnHeader title="Attachment ID" column={column} />,
        cell: ({ row }) => (
          <span className="font-mono text-xs">{row.original.business_id.substring(0, 8)}...</span>
        ),
        size: 120,
      },
      {
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => {
          const status = row.original.status;
          const variants: Record<string, 'destructive' | 'warning' | 'success' | 'secondary' | 'info'> = {
            failed: 'destructive',
            pending: 'warning',
            processing: 'secondary',
            sent: 'info',
            success: 'success',
          };
          return (
            <Badge variant={variants[status] || 'secondary'} appearance="ghost">
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
          const date = new Date(row.original.created_at);
          return formatDistanceToNow(date, { addSuffix: true });
        },
        size: 150,
      },
      {
        accessorKey: 'processed_at',
        header: ({ column }) => <DataGridColumnHeader title="Processed" column={column} />,
        cell: ({ row }) => {
          if (!row.original.processed_at) return '-';
          const date = new Date(row.original.processed_at);
          return formatDistanceToNow(date, { addSuffix: true });
        },
        size: 150,
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
              </SelectContent>
            </Select>
          </div>
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
