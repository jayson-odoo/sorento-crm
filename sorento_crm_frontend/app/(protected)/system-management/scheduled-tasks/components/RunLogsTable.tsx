'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  useReactTable,
  getCoreRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { useScheduledTaskRuns } from '../hooks/useScheduledTasks';
import type { ScheduledTaskRun as RunType } from '../types/scheduledTask.types';

interface RunLogsTableProps {
  taskId: string;
}

export function RunLogsTable({ taskId }: RunLogsTableProps) {
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: 20 });
  const page = pagination.pageIndex + 1;

  const { data, isLoading } = useScheduledTaskRuns(taskId, page, pagination.pageSize);
  const runs = data?.data ?? [];
  const total = data?.pagination?.total ?? 0;

  const columns = useMemo<ColumnDef<RunType>[]>(
    () => [
      {
        accessorKey: 'started_at',
        header: 'Started',
        cell: ({ row }) => formatDateTimeInMalaysia(row.original.started_at),
        size: 180,
      },
      {
        accessorKey: 'finished_at',
        header: 'Finished',
        cell: ({ row }) =>
          row.original.finished_at
            ? formatDateTimeInMalaysia(row.original.finished_at)
            : '-',
        size: 180,
      },
      {
        accessorKey: 'status',
        header: 'Status',
        cell: ({ row }) => (
          <Badge status={row.original.status}>
            {row.original.status}
          </Badge>
        ),
        size: 100,
      },
      {
        accessorKey: 'duration_ms',
        header: 'Duration',
        cell: ({ row }) => {
          const ms = row.original.duration_ms;
          return ms != null ? `${ms} ms` : '-';
        },
        size: 100,
      },
      {
        accessorKey: 'summary',
        header: 'Summary',
        cell: ({ row }) => {
          const s = row.original.summary;
          if (!s || typeof s !== 'object') return '-';
          const str = typeof s === 'string' ? s : JSON.stringify(s, null, 2);
          return (
            <pre className="text-muted-foreground text-xs whitespace-pre-wrap break-words max-h-32 overflow-auto rounded border bg-muted/30 p-2 font-sans">
              {str}
            </pre>
          );
        },
        size: 320,
      },
      {
        accessorKey: 'error',
        header: 'Error',
        cell: ({ row }) => {
          const err = row.original.error;
          if (!err) return '-';
          return (
            <pre className="text-destructive text-xs whitespace-pre-wrap break-words max-h-32 overflow-auto rounded border bg-destructive/5 p-2 font-sans">
              {err}
            </pre>
          );
        },
        size: 320,
      },
    ],
    [],
  );

  const table = useReactTable({
    data: runs,
    columns,
    state: { pagination },
    onPaginationChange: (updater) => {
      const next = typeof updater === 'function' ? updater(pagination) : updater;
      setPagination(next);
    },
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    pageCount: Math.ceil(total / pagination.pageSize) || 1,
  });

  return (
    <DataGrid
      table={table}
      recordCount={total}
      isLoading={isLoading}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
    >
      <Card>
        <CardHeader>
          <CardTable>
            <ScrollArea className="w-full">
              <DataGridTable />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          </CardTable>
        </CardHeader>
        <CardFooter className="flex justify-between border-t px-4 py-3">
          <DataGridPagination />
        </CardFooter>
      </Card>
    </DataGrid>
  );
}
