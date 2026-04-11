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
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Columns3, RefreshCw } from 'lucide-react';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { useQueryClient } from '@tanstack/react-query';
import { getImportJob } from '../services/importJobService';
import { useImportJobs, useCancelImportJob } from '../hooks/useImportJobs';
import type { ImportJob } from '../types/importJob.types';
import { toast } from 'sonner';
import { getStatusBadgeVariant } from '@/lib/status-badge';

const JOB_TYPE_LABELS: Record<string, string> = {
  order_import: 'Order Import',
  order_tracking_import: 'Order Tracking Import',
  product_import: 'Product Import',
  stock_import: 'Stock Import',
  spo_import: 'SPO Import',
  attachment_bulk_import: 'Attachment Bulk Import',
  grn_listing_import: 'Upload GRN',
  grn_lines_import: 'Upload GRN Lines',
};

function getJobTypeLabel(jobType: string): string {
  return JOB_TYPE_LABELS[jobType] ?? jobType;
}

export default function ImportJobsList() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [jobType, setJobType] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [cancelingJobId, setCancelingJobId] = useState<string | null>(null);
  const [refreshingJobId, setRefreshingJobId] = useState<string | null>(null);

  const { data, isLoading, refetch, isFetching } = useImportJobs({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    job_type: jobType || undefined,
    status: statusFilter || undefined,
  });
  const cancelJobMutation = useCancelImportJob();

  const columns = useMemo<ColumnDef<ImportJob>[]>(
    () => [
      {
        accessorKey: 'job_type',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        cell: ({ row }) => (
          <Badge variant="secondary" appearance="ghost">
            {getJobTypeLabel(row.original.job_type)}
          </Badge>
        ),
        size: 140,
        minSize: 80,
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <Badge variant={getStatusBadgeVariant(row.original.status)}>
            {(row.original.status || '').toUpperCase()}
          </Badge>
        ),
        size: 120,
        minSize: 80,
      },
      {
        accessorKey: 'filename',
        header: ({ column }) => <DataGridColumnHeader title="Filename" column={column} />,
        cell: ({ row }) => {
          const f = row.original.filename || '-';
          return (
            <span className="block truncate" title={f}>
              {f}
            </span>
          );
        },
        size: 300,
        minSize: 180,
      },
      {
        accessorKey: 'total_rows',
        header: ({ column }) => <DataGridColumnHeader title="Total Rows" column={column} />,
        cell: ({ row }) => row.original.total_rows,
        size: 100,
        minSize: 70,
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
        size: 160,
        minSize: 120,
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
        accessorKey: 'skipped_rows',
        header: ({ column }) => <DataGridColumnHeader title="Skipped" column={column} />,
        cell: ({ row }) => (
          <span className="text-amber-600 font-medium">{row.original.skipped_rows}</span>
        ),
        size: 100,
        minSize: 70,
      },
      {
        accessorKey: 'created_at',
        header: ({ column }) => <DataGridColumnHeader title="Created At" column={column} />,
        cell: ({ row }) => formatDateTimeInMalaysia(row.original.created_at),
        size: 200,
      },
      {
        accessorKey: 'started_at',
        header: ({ column }) => <DataGridColumnHeader title="Started At" column={column} />,
        cell: ({ row }) => row.original.started_at ? formatDateTimeInMalaysia(row.original.started_at) : '-',
        size: 200,
      },
      {
        accessorKey: 'completed_at',
        header: ({ column }) => <DataGridColumnHeader title="Completed At" column={column} />,
        cell: ({ row }) => row.original.completed_at ? formatDateTimeInMalaysia(row.original.completed_at) : '-',
        size: 200,
      },
      {
        accessorKey: 'updated_at',
        header: ({ column }) => <DataGridColumnHeader title="Updated At" column={column} />,
        cell: ({ row }) => row.original.updated_at ? formatDateTimeInMalaysia(row.original.updated_at) : '-',
        size: 200,
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: ({ row }) => {
          const job = row.original;
          const status = job.status;
          const canCancel = ['pending', 'queued', 'started'].includes(status);
          const isRefreshing = refreshingJobId === job.job_id;
          const isCancelling = cancelingJobId === job.job_id && cancelJobMutation.isPending;
          const handleRefresh = async (e: React.MouseEvent) => {
            e.stopPropagation();
            setRefreshingJobId(job.job_id);
            try {
              const updatedJob = await getImportJob(job.job_id);
              queryClient.setQueryData(
                ['import-jobs', pagination.pageIndex, pagination.pageSize, jobType || undefined, statusFilter || undefined],
                (old: { data: ImportJob[]; pagination: { total: number }; empty: boolean } | undefined) => {
                  if (!old) return old;
                  return {
                    ...old,
                    data: old.data.map((j) => (j.job_id === job.job_id ? updatedJob : j)),
                  };
                },
              );
              toast.success('Job refreshed');
            } catch (err) {
              toast.error(err instanceof Error ? err.message : 'Failed to refresh job');
            } finally {
              setRefreshingJobId(null);
            }
          };
          return (
            <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
              <Button
                variant="ghost"
                size="sm"
                disabled={isRefreshing}
                onClick={handleRefresh}
                title="Refresh this job"
                className="h-8 w-8 p-0"
              >
                <RefreshCw className={`size-4 ${isRefreshing ? 'animate-spin' : ''}`} />
              </Button>
              {canCancel && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={isCancelling}
                  onClick={(e) => {
                    e.stopPropagation();
                    setCancelingJobId(job.job_id);
                    cancelJobMutation.mutate(job.job_id, {
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
                  {isCancelling ? 'Cancelling...' : 'Cancel'}
                </Button>
              )}
            </div>
          );
        },
        size: 140,
      },
    ],
    [
      cancelJobMutation.isPending,
      cancelingJobId,
      refreshingJobId,
      pagination.pageIndex,
      pagination.pageSize,
      jobType,
      statusFilter,
      queryClient,
    ],
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
    columnResizeMode: 'onChange',
  });

  const handleRowClick = (jobId: string) => {
    const params = new URLSearchParams({
      page: String(pagination.pageIndex + 1),
      pageSize: String(pagination.pageSize),
    });
    router.push(`/system-management/import-jobs/${jobId}?${params.toString()}`);
  };

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      onRowClick={(row) => handleRowClick(row.job_id)}
      tableLayout={{ columnsVisibility: true,  width: 'fixed', columnsResizable: true }}
      onRefresh={() => void refetch()}
      isRefreshing={isFetching && !isLoading}
    >
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-3">
          <div className="flex gap-2 items-center">
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
            <DataGridColumnVisibility
              table={table}
              trigger={
                <Button variant="outline" size="sm" className="gap-1">
                  <Columns3 className="size-4" />
                  Columns
                </Button>
              }
            />
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
