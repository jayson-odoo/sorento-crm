'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  useReactTable,
  getCoreRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { RefreshCw } from 'lucide-react';
import { formatDateTime } from '@/lib/helpers';
import { useImportJobs, useCancelImportJob } from '../hooks/useImportJobs';
import type { ImportJob } from '../types/importJob.types';
import { toast } from 'sonner';

export default function ImportJobsList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [jobType, setJobType] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [cancelingJobId, setCancelingJobId] = useState<string | null>(null);

  const { data, isLoading, refetch } = useImportJobs({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    job_type: jobType || undefined,
    status: statusFilter || undefined,
  });
  const cancelJobMutation = useCancelImportJob();

  const getStatusBadge = (status: string) => {
    const variants: Record<string, { variant: 'primary' | 'secondary' | 'destructive' | 'outline'; appearance?: 'ghost' }> = {
      pending: { variant: 'outline' },
      queued: { variant: 'secondary' },
      started: { variant: 'secondary', appearance: 'ghost' },
      finished: { variant: 'primary' },
      failed: { variant: 'destructive' },
      cancelled: { variant: 'outline' },
    };
    const config = variants[status] || { variant: 'secondary' };
    return (
      <Badge {...config}>
        {status.toUpperCase()}
      </Badge>
    );
  };

  const columns = useMemo<ColumnDef<ImportJob>[]>(
    () => [
      {
        accessorKey: 'job_type',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        cell: ({ row }) => (
          <Badge variant="secondary" appearance="ghost">
            {row.original.job_type}
          </Badge>
        ),
        size: 140,
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => getStatusBadge(row.original.status),
        size: 120,
      },
      {
        accessorKey: 'filename',
        header: ({ column }) => <DataGridColumnHeader title="Filename" column={column} />,
        cell: ({ row }) => row.original.filename || '-',
        size: 220,
      },
      {
        accessorKey: 'total_rows',
        header: ({ column }) => <DataGridColumnHeader title="Total Rows" column={column} />,
        cell: ({ row }) => row.original.total_rows,
        size: 100,
      },
      {
        accessorKey: 'processed_rows',
        header: ({ column }) => <DataGridColumnHeader title="Processed" column={column} />,
        cell: ({ row }) => {
          const { processed_rows, total_rows } = row.original;
          const percentage = total_rows > 0 ? Math.round((processed_rows / total_rows) * 100) : 0;
          return (
            <div className="flex items-center gap-2">
              <span>{processed_rows} / {total_rows}</span>
              {total_rows > 0 && (
                <span className="text-xs text-muted-foreground">({percentage}%)</span>
              )}
            </div>
          );
        },
        size: 140,
      },
      {
        accessorKey: 'successful_rows',
        header: ({ column }) => <DataGridColumnHeader title="Success" column={column} />,
        cell: ({ row }) => (
          <span className="text-emerald-600 font-medium">{row.original.successful_rows}</span>
        ),
        size: 100,
      },
      {
        accessorKey: 'failed_rows',
        header: ({ column }) => <DataGridColumnHeader title="Failed" column={column} />,
        cell: ({ row }) => (
          <span className="text-red-600 font-medium">{row.original.failed_rows}</span>
        ),
        size: 100,
      },
      {
        accessorKey: 'created_at',
        header: ({ column }) => <DataGridColumnHeader title="Created At" column={column} />,
        cell: ({ row }) => formatDateTime(new Date(row.original.created_at)),
        size: 200,
      },
      {
        accessorKey: 'started_at',
        header: ({ column }) => <DataGridColumnHeader title="Started At" column={column} />,
        cell: ({ row }) => row.original.started_at ? formatDateTime(new Date(row.original.started_at)) : '-',
        size: 200,
      },
      {
        accessorKey: 'completed_at',
        header: ({ column }) => <DataGridColumnHeader title="Completed At" column={column} />,
        cell: ({ row }) => row.original.completed_at ? formatDateTime(new Date(row.original.completed_at)) : '-',
        size: 200,
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: ({ row }) => {
          const status = row.original.status;
          const canCancel = ['pending', 'queued', 'started'].includes(status);
          if (!canCancel) return null;
          const isLoading = cancelingJobId === row.original.job_id && cancelJobMutation.isPending;
          return (
            <Button
              variant="outline"
              size="sm"
              disabled={isLoading}
              onClick={(event) => {
                event.stopPropagation();
                setCancelingJobId(row.original.job_id);
                cancelJobMutation.mutate(row.original.job_id, {
                  onSuccess: (data) => {
                    toast.success(data.message || 'Job cancelled');
                    setCancelingJobId(null);
                  },
                  onError: (error) => {
                    toast.error(error instanceof Error ? error.message : 'Failed to cancel job');
                    setCancelingJobId(null);
                  },
                });
              }}
            >
              {isLoading ? 'Cancelling...' : 'Cancel'}
            </Button>
          );
        },
        size: 120,
      },
    ],
    [cancelJobMutation.isPending, cancelingJobId],
  );

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.job_id,
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
  });

  const handleRowClick = (jobId: string) => {
    router.push(`/system-management/import-jobs/${jobId}`);
  };

  return (
    <DataGrid 
      table={table} 
      recordCount={data?.pagination.total || 0} 
      isLoading={isLoading}
      onRowClick={(row) => handleRowClick(row.job_id)}
    >
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-3">
          <div className="flex gap-2">
            <Input
              placeholder="Filter by type..."
              value={jobType}
              onChange={(e) => setJobType(e.target.value)}
              className="w-48"
            />
            <Input
              placeholder="Filter by status..."
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-48"
            />
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                refetch();
                toast.success('List refreshed');
              }}
              disabled={isLoading}
            >
              <RefreshCw className={`size-4 ${isLoading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
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
