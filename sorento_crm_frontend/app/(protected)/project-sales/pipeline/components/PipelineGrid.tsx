'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import type { Project } from '../../_shared/types/project.types';

/**
 * The management view of the same pipeline (AC-G5).
 *
 * Fixed layout with explicit sizes and `truncate` + `title` on every long cell, so a
 * verbose project title cannot push the value and owner columns off screen.
 */
export function PipelineGrid({
  projects,
  total,
  isLoading,
  isFetching,
  pagination,
  onPaginationChange,
  sorting,
  onSortingChange,
  onRefresh,
  searchSlot,
}: {
  projects: Project[];
  total: number;
  isLoading?: boolean;
  isFetching?: boolean;
  pagination: PaginationState;
  onPaginationChange: (next: PaginationState) => void;
  sorting: SortingState;
  onSortingChange: (next: SortingState) => void;
  onRefresh: () => void;
  searchSlot?: React.ReactNode;
}) {
  const [columnVisibility, setColumnVisibility] = useState({});

  const columns = useMemo<ColumnDef<Project>[]>(
    () => [
      {
        accessorKey: 'project_code',
        header: ({ column }) => <DataGridColumnHeader title="Code" column={column} />,
        size: 120,
        cell: ({ row }) => (
          <Link
            href={`/project-sales/${row.original.id}`}
            className="font-mono text-xs hover:underline"
          >
            {row.original.project_code}
          </Link>
        ),
      },
      {
        accessorKey: 'title',
        header: ({ column }) => <DataGridColumnHeader title="Project" column={column} />,
        size: 260,
        cell: ({ row }) => (
          <Link
            href={`/project-sales/${row.original.id}`}
            className="block truncate hover:underline"
            title={row.original.title}
          >
            {row.original.title}
          </Link>
        ),
      },
      {
        id: 'developer_name',
        accessorFn: (row) => row.developer_name ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Developer" column={column} />,
        size: 180,
        enableSorting: false,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.developer_name ?? ''}>
            {row.original.developer_name ?? <Muted>Not set</Muted>}
          </span>
        ),
      },
      {
        id: 'status_label',
        accessorFn: (row) => row.status_label ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Stage" column={column} />,
        size: 140,
        enableSorting: false,
        cell: ({ row }) =>
          row.original.status_label ? (
            <Badge variant="secondary" className="truncate">
              {row.original.status_label}
            </Badge>
          ) : (
            <Muted>No stage</Muted>
          ),
      },
      {
        accessorKey: 'outcome',
        header: ({ column }) => <DataGridColumnHeader title="Outcome" column={column} />,
        size: 110,
        cell: ({ row }) => (
          <Badge
            variant={row.original.outcome === 'open' ? 'outline' : 'secondary'}
            className="capitalize"
          >
            {row.original.outcome}
          </Badge>
        ),
      },
      {
        id: 'estimated_sales_value',
        accessorFn: (row) => row.estimated_sales_value ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Estimated" column={column} />,
        size: 130,
        enableSorting: false,
        cell: ({ row }) =>
          row.original.estimated_sales_value ? (
            <span className="tabular-nums">
              {formatMyr(row.original.estimated_sales_value)}
            </span>
          ) : (
            <Muted>Not set</Muted>
          ),
      },
      {
        id: 'brands',
        accessorFn: (row) => row.brands.join(', '),
        header: ({ column }) => <DataGridColumnHeader title="Brands" column={column} />,
        size: 150,
        enableSorting: false,
        cell: ({ row }) =>
          row.original.brands.length ? (
            <span className="block truncate" title={row.original.brands.join(', ')}>
              {row.original.brands.join(', ')}
            </span>
          ) : (
            <Muted>None</Muted>
          ),
      },
      {
        id: 'owner_name',
        accessorFn: (row) => row.owner_name ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Owner" column={column} />,
        size: 150,
        enableSorting: false,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.owner_name ?? ''}>
            {row.original.owner_name ?? <Muted>Unassigned</Muted>}
          </span>
        ),
      },
      {
        id: 'next_action',
        // Derived server-side from the earliest open task. Not sortable: the backend
        // sorts on real columns only, and a client-side sort of one page would order
        // the visible rows while lying about the rest.
        header: ({ column }) => <DataGridColumnHeader title="Next action" column={column} />,
        size: 150,
        enableSorting: false,
        cell: ({ row }) =>
          row.original.next_action_date ? (
            <span
              className={
                row.original.next_action_overdue
                  ? 'block truncate font-medium text-destructive'
                  : 'block truncate'
              }
              title={
                row.original.next_action_overdue
                  ? `${formatGridDate(row.original.next_action_date)}, overdue`
                  : formatGridDate(row.original.next_action_date)
              }
            >
              {formatGridDate(row.original.next_action_date)}
            </span>
          ) : row.original.open_task_count > 0 ? (
            <Muted>{row.original.open_task_count} open, none dated</Muted>
          ) : (
            <Muted>Nothing open</Muted>
          ),
      },
      {
        accessorKey: 'last_meaningful_activity_at',
        header: ({ column }) => <DataGridColumnHeader title="Last activity" column={column} />,
        size: 130,
        cell: ({ row }) =>
          row.original.days_since_last_activity === null ||
          row.original.days_since_last_activity === undefined ? (
            <Muted>No activity</Muted>
          ) : (
            <span className="tabular-nums">
              {row.original.days_since_last_activity === 0
                ? 'today'
                : `${row.original.days_since_last_activity}d ago`}
            </span>
          ),
      },
      {
        id: 'flags',
        header: () => <span className="text-xs">Flags</span>,
        size: 110,
        enableSorting: false,
        cell: ({ row }) =>
          row.original.is_critical ? (
            <Badge variant="destructive">Critical</Badge>
          ) : (
            <Muted>-</Muted>
          ),
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: projects,
    pageCount: Math.max(1, Math.ceil(total / Math.max(pagination.pageSize, 1))),
    getRowId: (row) => row.id,
    state: { pagination, sorting, columnVisibility },
    onColumnVisibilityChange: setColumnVisibility,
    onPaginationChange: (updater) =>
      onPaginationChange(
        typeof updater === 'function' ? updater(pagination) : updater,
      ),
    onSortingChange: (updater) =>
      onSortingChange(typeof updater === 'function' ? updater(sorting) : updater),
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
    defaultColumn: { minSize: 60, maxSize: 800, size: 150 },
  });

  return (
    <DataGrid
      table={table}
      recordCount={total}
      isLoading={isLoading}
      standardToolbar={false}
      tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
      emptyMessage="No projects match these filters."
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={searchSlot}
            exportConfig={{ filename: 'projects_export.xlsx' }}
            onRefresh={onRefresh}
            isRefreshing={Boolean(isFetching) && !isLoading}
          />
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

function Muted({ children }: { children: React.ReactNode }) {
  return <span className="text-muted-foreground">{children}</span>;
}

function formatMyr(value: string): string {
  const amount = Number(value);
  if (Number.isNaN(amount)) return value;
  return `RM ${amount.toLocaleString('en-MY', { maximumFractionDigits: 0 })}`;
}

function formatGridDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString('en-MY', { day: '2-digit', month: 'short', year: 'numeric' });
}
