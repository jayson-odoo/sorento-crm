'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
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
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { useScheduledTasks } from '../hooks/useScheduledTasks';
import type { ScheduledTask } from '../types/scheduledTask.types';
import { getStatusBadgeVariant } from '@/lib/status-badge';
import { ChevronRight } from 'lucide-react';

const INTERVAL_LABELS: Record<string, string> = {
  seconds: 'sec',
  minutes: 'min',
  hours: 'hr',
  days: 'day',
};

function formatFrequency(task: ScheduledTask): string {
  const unit = INTERVAL_LABELS[task.interval_unit] ?? task.interval_unit;
  return `Every ${task.interval_value} ${unit}${task.interval_value !== 1 ? 's' : ''}`;
}

export default function ScheduledTasksList() {
  const router = useRouter();
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: 50 });

  const { data, isLoading } = useScheduledTasks();
  const tasks = data?.data ?? [];
  const total = data?.pagination?.total ?? 0;

  const columns = useMemo<ColumnDef<ScheduledTask>[]>(
    () => [
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span className="font-medium">{row.original.name}</span>
            {row.original.description && (
              <span className="text-xs text-muted-foreground truncate max-w-[200px]">
                {row.original.description}
              </span>
            )}
          </div>
        ),
        size: 220,
        minSize: 140,
        meta: { skeleton: <Skeleton className="h-8 w-40" /> },
      },
      {
        accessorKey: 'key',
        header: ({ column }) => <DataGridColumnHeader title="Key" column={column} />,
        cell: ({ row }) => (
          <Badge variant="secondary" appearance="ghost">
            {row.original.key}
          </Badge>
        ),
        size: 180,
        minSize: 100,
      },
      {
        accessorKey: 'enabled',
        header: ({ column }) => <DataGridColumnHeader title="Enabled" column={column} />,
        cell: ({ row }) => (
          <Badge variant={row.original.enabled ? 'success' : 'secondary'}>
            {row.original.enabled ? 'Yes' : 'No'}
          </Badge>
        ),
        size: 90,
      },
      {
        accessorKey: 'interval',
        header: ({ column }) => <DataGridColumnHeader title="Frequency" column={column} />,
        cell: ({ row }) => formatFrequency(row.original),
        size: 120,
      },
      {
        accessorKey: 'next_run_at',
        header: ({ column }) => <DataGridColumnHeader title="Next Run" column={column} />,
        cell: ({ row }) =>
          row.original.next_run_at
            ? formatDateTimeInMalaysia(row.original.next_run_at)
            : '-',
        size: 160,
      },
      {
        accessorKey: 'last_run_at',
        header: ({ column }) => <DataGridColumnHeader title="Last Run" column={column} />,
        cell: ({ row }) =>
          row.original.last_run_at
            ? formatDateTimeInMalaysia(row.original.last_run_at)
            : '-',
        size: 160,
      },
      {
        accessorKey: 'last_status',
        header: ({ column }) => <DataGridColumnHeader title="Last Status" column={column} />,
        cell: ({ row }) => {
          const status = row.original.last_status || '-';
          return (
            <Badge variant={getStatusBadgeVariant(status)}>
              {status}
            </Badge>
          );
        },
        size: 100,
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0"
            onClick={() => router.push(`/system-management/scheduled-tasks/${row.original.id}`)}
          >
            <ChevronRight className="size-4" />
          </Button>
        ),
        size: 60,
      },
    ],
    [router],
  );

  const table = useReactTable({
    data: tasks,
    columns,
    state: { pagination },
    onPaginationChange: (updater) => {
      const next = typeof updater === 'function' ? updater(pagination) : updater;
      setPagination(next);
    },
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: false,
    pageCount: Math.ceil(total / pagination.pageSize) || 1,
  });

  return (
    <DataGrid
      table={table}
      recordCount={total}
      isLoading={isLoading}
      onRowClick={(task) => task?.id && router.push(`/system-management/scheduled-tasks/${task.id}`)}
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
