'use client';

/**
 * System Management > Scheduled Tasks (SCHEDULED-TASKS-GRID, owner 9 Nov 2026).
 *
 * The standard list stack (`DataGrid` + `DataGridListToolbar` + `buildSelectColumn`, query
 * through `buildDataGridParams`), the same one `procurement-management/packing-lists` uses:
 * page, sort and search run on the server; every column sorts; every filter is multi-select.
 * ONE line per row: no cell stacks a second line, long text truncates and carries its full
 * value in `title`. The description and the Enabled switch + Run now live on the detail page.
 */

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  SortingState,
  VisibilityState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useResetPageOnFilterChange } from '@/hooks/useResetPageOnFilterChange';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { formatStatusLabel } from '@/lib/status-badge';
import { useScheduledTasks } from '../hooks/useScheduledTasks';
import type { ScheduledTask } from '../types/scheduledTask.types';

const INTERVAL_LABELS: Record<string, string> = {
  seconds: 'sec',
  minutes: 'min',
  hours: 'hr',
  days: 'day',
};

export const ENABLED_OPTIONS = [
  { value: 'true', label: 'Enabled' },
  { value: 'false', label: 'Disabled' },
];

export const LAST_STATUS_OPTIONS = [
  { value: 'success', label: 'Success' },
  { value: 'failed', label: 'Failed' },
  { value: 'skipped', label: 'Skipped' },
  { value: 'started', label: 'Started' },
  { value: 'never', label: 'Never run' },
];

export const FREQUENCY_OPTIONS = [
  { value: 'seconds', label: 'Seconds' },
  { value: 'minutes', label: 'Minutes' },
  { value: 'hours', label: 'Hours' },
  { value: 'days', label: 'Days' },
];

export function formatFrequency(task: Pick<ScheduledTask, 'interval_unit' | 'interval_value'>): string {
  const unit = INTERVAL_LABELS[task.interval_unit] ?? task.interval_unit;
  return `Every ${task.interval_value} ${unit}${task.interval_value !== 1 ? 's' : ''}`;
}

/** One line, always: the cell clips and the full value is the hover title. */
function OneLine({ text, className }: { text: string; className?: string }) {
  return (
    <span className={`block truncate ${className ?? ''}`} title={text}>
      {text}
    </span>
  );
}

function dateCell(value: string | null) {
  return value ? <OneLine text={formatDateTimeInMalaysia(value)} className="tabular-nums" /> : <OneLine text="-" />;
}

export default function ScheduledTasksList() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'name', desc: false }]);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({ key: false });
  const [enabled, setEnabled] = useState<string[]>([]);
  const [lastStatus, setLastStatus] = useState<string[]>([]);
  const [frequency, setFrequency] = useState<string[]>([]);
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: searchQuery,
    isSettling: searchSettling,
  } = useDebouncedSearch();

  useResetPageOnFilterChange(setPagination, [enabled, lastStatus, frequency, searchQuery]);

  const { data, isLoading, isPlaceholderData, isFetching, refetch, error } = useScheduledTasks({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    enabled,
    last_status: lastStatus,
    interval_unit: frequency,
  });
  const tasks = data?.data ?? [];
  const total = data?.pagination?.total ?? 0;

  const columns = useMemo<ColumnDef<ScheduledTask>[]>(
    () => [
      buildSelectColumn<ScheduledTask>({ rowLabel: (row) => `Select ${row.original.name}` }),
      {
        id: 'name',
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Name" visibility column={column} />,
        cell: ({ row }) => <OneLine text={row.original.name} className="font-medium" />,
        size: 240,
        minSize: 140,
        enableHiding: false,
        meta: { headerTitle: 'Name' },
      },
      {
        id: 'key',
        accessorKey: 'key',
        header: ({ column }) => <DataGridColumnHeader title="Key" visibility column={column} />,
        cell: ({ row }) => <OneLine text={row.original.key} className="font-mono text-xs" />,
        size: 200,
        meta: { headerTitle: 'Key' },
      },
      {
        id: 'frequency',
        accessorFn: (row) => formatFrequency(row),
        header: ({ column }) => <DataGridColumnHeader title="Frequency" visibility column={column} />,
        cell: ({ row }) => <OneLine text={formatFrequency(row.original)} />,
        size: 130,
        meta: { headerTitle: 'Frequency' },
      },
      {
        id: 'enabled',
        accessorKey: 'enabled',
        header: ({ column }) => <DataGridColumnHeader title="Enabled" visibility column={column} />,
        cell: ({ row }) => (
          <Badge variant={row.original.enabled ? 'success' : 'secondary'} appearance="light">
            {row.original.enabled ? 'Enabled' : 'Disabled'}
          </Badge>
        ),
        size: 110,
        meta: { headerTitle: 'Enabled' },
      },
      {
        id: 'last_status',
        accessorKey: 'last_status',
        header: ({ column }) => <DataGridColumnHeader title="Last status" visibility column={column} />,
        cell: ({ row }) =>
          row.original.last_status ? (
            <Badge status={row.original.last_status}>{formatStatusLabel(row.original.last_status)}</Badge>
          ) : (
            <OneLine text="Never run" className="text-muted-foreground" />
          ),
        size: 120,
        meta: { headerTitle: 'Last status' },
      },
      {
        id: 'last_run_at',
        accessorKey: 'last_run_at',
        header: ({ column }) => <DataGridColumnHeader title="Last run" visibility column={column} />,
        cell: ({ row }) => dateCell(row.original.last_run_at),
        size: 190,
        meta: { headerTitle: 'Last run' },
      },
      {
        id: 'next_run_at',
        accessorKey: 'next_run_at',
        header: ({ column }) => <DataGridColumnHeader title="Next run" visibility column={column} />,
        cell: ({ row }) => dateCell(row.original.next_run_at),
        size: 190,
        meta: { headerTitle: 'Next run' },
      },
      {
        id: 'last_error',
        accessorKey: 'last_error',
        header: ({ column }) => <DataGridColumnHeader title="Last error" visibility column={column} />,
        cell: ({ row }) =>
          row.original.last_error ? (
            <OneLine text={row.original.last_error} className="text-destructive" />
          ) : (
            <OneLine text="-" className="text-muted-foreground" />
          ),
        size: 320,
        minSize: 120,
        meta: { headerTitle: 'Last error' },
      },
    ],
    [],
  );

  const table = useReactTable({
    data: tasks,
    columns,
    getRowId: (row) => row.id,
    pageCount: Math.ceil(total / pagination.pageSize) || 1,
    state: { pagination, sorting, rowSelection, columnVisibility },
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    columnResizeMode: 'onChange',
  });

  const activeFilters = [enabled, lastStatus, frequency].filter((v) => v.length > 0).length;

  return (
    <DataGrid
      table={table}
      recordCount={total}
      isLoading={isLoading}
      isPlaceholderData={isPlaceholderData}
      error={error}
      onRetry={() => void refetch()}
      rowHref={(task) => `/system-management/scheduled-tasks/${task.id}`}
      tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
      emptyMessage={
        activeFilters > 0 || searchQuery ? 'No scheduled tasks match your filters.' : 'No scheduled tasks yet.'
      }
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <ListSearchInput
                value={searchInput}
                onChange={setSearchInput}
                isSettling={isSearchInFlight(searchSettling, isFetching, searchQuery)}
                placeholder="Search name, key or error"
                className="w-full sm:w-64"
              />
            }
            filters={{
              kind: 'custom',
              active: activeFilters > 0,
              activeCount: activeFilters,
              content: (
                <div className="space-y-4">
                  <div>
                    <Label htmlFor="scheduled-task-enabled-filter">Enabled</Label>
                    <SearchableMultiSelect
                      id="scheduled-task-enabled-filter"
                      value={enabled}
                      onChange={setEnabled}
                      options={ENABLED_OPTIONS}
                      placeholder="Any"
                      triggerClassName="mt-1"
                      clearable
                    />
                  </div>
                  <div>
                    <Label htmlFor="scheduled-task-status-filter">Last status</Label>
                    <SearchableMultiSelect
                      id="scheduled-task-status-filter"
                      value={lastStatus}
                      onChange={setLastStatus}
                      options={LAST_STATUS_OPTIONS}
                      placeholder="Any"
                      triggerClassName="mt-1"
                      clearable
                    />
                  </div>
                  <div>
                    <Label htmlFor="scheduled-task-frequency-filter">Frequency</Label>
                    <SearchableMultiSelect
                      id="scheduled-task-frequency-filter"
                      value={frequency}
                      onChange={setFrequency}
                      options={FREQUENCY_OPTIONS}
                      placeholder="Any"
                      triggerClassName="mt-1"
                      clearable
                    />
                  </div>
                </div>
              ),
            }}
            exportConfig={{ filename: 'scheduled_tasks_export.xlsx' }}
            onRefresh={() => void refetch()}
            isRefreshing={isFetching && !isLoading}
          />
        </CardHeader>
        <CardTable>
          <DataGridTable />
        </CardTable>
        <CardFooter className="flex justify-between border-t px-4 py-3">
          <DataGridPagination />
        </CardFooter>
      </Card>
    </DataGrid>
  );
}
