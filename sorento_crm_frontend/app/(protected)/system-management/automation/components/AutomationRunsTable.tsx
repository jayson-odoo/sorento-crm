'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Card, CardFooter, CardHeader, CardTable, CardTitle } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { useAutomationRuns } from '../hooks/useAutomations';
import type { AutomationRun } from '../types/automation.types';

const STATUS_VARIANT: Record<string, 'success' | 'destructive' | 'secondary' | 'warning'> = {
  success: 'success',
  failed: 'destructive',
  partial: 'warning',
  running: 'secondary',
};

export default function AutomationRunsTable({ automationId }: { automationId: string }) {
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: 25 });
  const { data, isLoading, isFetching, refetch } = useAutomationRuns(
    automationId,
    pagination.pageIndex + 1,
    pagination.pageSize,
  );

  const rows = data?.data ?? [];
  const total = data?.pagination?.total ?? 0;

  const columns = useMemo<ColumnDef<AutomationRun>[]>(
    () => [
      {
        accessorKey: 'started_at',
        header: ({ column }) => <DataGridColumnHeader title="Started" column={column} />,
        cell: ({ row }) => formatDateTimeInMalaysia(row.original.started_at),
        size: 160,
      },
      {
        accessorKey: 'run_mode',
        header: ({ column }) => <DataGridColumnHeader title="Mode" column={column} />,
        cell: ({ row }) => row.original.run_mode,
        size: 100,
      },
      {
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <Badge variant={STATUS_VARIANT[row.original.status] ?? 'secondary'}>
            {row.original.status}
          </Badge>
        ),
        size: 100,
      },
      {
        accessorKey: 'recipients_attempted',
        header: ({ column }) => <DataGridColumnHeader title="Attempted" column={column} />,
        cell: ({ row }) => row.original.recipients_attempted,
        size: 90,
      },
      {
        accessorKey: 'recipients_delivered',
        header: ({ column }) => <DataGridColumnHeader title="Delivered" column={column} />,
        cell: ({ row }) => row.original.recipients_delivered,
        size: 90,
      },
      {
        accessorKey: 'duration_ms',
        header: ({ column }) => <DataGridColumnHeader title="Duration" column={column} />,
        cell: ({ row }) => (row.original.duration_ms != null ? `${row.original.duration_ms} ms` : '-'),
        size: 100,
      },
      {
        accessorKey: 'error',
        header: ({ column }) => <DataGridColumnHeader title="Error" column={column} />,
        cell: ({ row }) => (
          <span className="truncate max-w-[260px] block text-destructive" title={row.original.error ?? ''}>
            {row.original.error ?? ''}
          </span>
        ),
        size: 280,
      },
    ],
    [],
  );

  const table = useReactTable({
    data: rows,
    columns,
    state: { pagination },
    onPaginationChange: (updater) => {
      const next = typeof updater === 'function' ? updater(pagination) : updater;
      setPagination(next);
    },
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    pageCount: Math.max(1, Math.ceil(total / pagination.pageSize)),
  });

  return (
    <DataGrid
      table={table}
      recordCount={total}
      isLoading={isLoading}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      onRefresh={() => void refetch()}
      isRefreshing={isFetching && !isLoading}
    >
      <Card>
        <CardHeader>
          <CardTitle>Run history</CardTitle>
        </CardHeader>
        <CardTable>
          <ScrollArea className="w-full">
            <DataGridTable />
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </CardTable>
        {total > pagination.pageSize && (
          <CardFooter className="flex justify-between border-t px-4 py-3">
            <DataGridPagination />
          </CardFooter>
        )}
      </Card>
    </DataGrid>
  );
}
