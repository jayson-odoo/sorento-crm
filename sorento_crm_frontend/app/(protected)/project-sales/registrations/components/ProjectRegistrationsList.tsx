'use client';

import { useMemo, useState } from 'react';
import {
  type ColumnDef,
  PaginationState,
  SortingState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useListStateFromUrl } from '@/hooks/useListStateFromUrl';
import { useResetPageOnFilterChange } from '@/hooks/useResetPageOnFilterChange';
import { buildDetailSearch } from '@/lib/listNavQuery';
import { formatDateInMalaysia } from '@/lib/helpers';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import type { ProjectRegistrationRow } from '@/types/projectRegistration';
import { useProjectRegistrations } from '../hooks/useProjectRegistrations';
import { ProjectRegistrationDuplicates } from './ProjectRegistrationDuplicates';

const BASE_PATH = '/project-sales/registrations';

export const REGISTRATION_STATUS_LABELS: Record<string, string> = {
  draft: 'Draft',
  pending: 'Pending',
  approved: 'Approved',
  rejected: 'Rejected',
};

const STATUS_OPTIONS = [
  { value: 'pending', label: 'Pending' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'all', label: 'All statuses' },
];

const truncated = (value: string | null | undefined) => (
  <span className="truncate" title={value ?? undefined}>
    {value || '-'}
  </span>
);

export default function ProjectRegistrationsList() {
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });
  const [sorting, setSorting] = useState<SortingState>([]);
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: searchQuery,
    isSettling: searchSettling,
    reset: resetSearch,
  } = useDebouncedSearch();
  const [statusFilter, setStatusFilter] = useState('pending');

  useListStateFromUrl((state) => {
    setPagination({ pageIndex: state.pageIndex, pageSize: state.pageSize });
    setSorting(state.sorting);
    resetSearch(state.searchQuery);
    setStatusFilter(state.filters.status ?? 'pending');
  });

  const { data, isLoading, isPlaceholderData, refetch, isFetching, error } =
    useProjectRegistrations({
      pageIndex: pagination.pageIndex,
      pageSize: pagination.pageSize,
      sorting,
      searchQuery,
      status: statusFilter,
    });

  useResetPageOnFilterChange(setPagination, [statusFilter, searchQuery]);

  const rowHref = (row: ProjectRegistrationRow) => {
    const search = buildDetailSearch(
      {
        pageIndex: pagination.pageIndex,
        pageSize: pagination.pageSize,
        sorting,
        searchQuery,
      },
      { status: statusFilter !== 'pending' ? statusFilter : undefined },
    );
    return `${BASE_PATH}/${row.id}${search ? `?${search}` : ''}`;
  };

  const columns = useMemo<ColumnDef<ProjectRegistrationRow>[]>(
    () => [
      {
        id: 'submitted_at',
        accessorKey: 'submitted_at',
        header: ({ column }) => <DataGridColumnHeader title="Date" column={column} />,
        size: 120,
        cell: ({ row }) =>
          row.original.submitted_at ? formatDateInMalaysia(row.original.submitted_at) : '-',
        meta: { headerTitle: 'Date', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'title',
        header: ({ column }) => <DataGridColumnHeader title="Project title" column={column} />,
        size: 280,
        enableSorting: false,
        cell: ({ row }) => truncated(row.original.title),
        meta: { headerTitle: 'Project title', skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        accessorKey: 'developer_name',
        header: ({ column }) => <DataGridColumnHeader title="Developer" column={column} />,
        size: 200,
        enableSorting: false,
        cell: ({ row }) => truncated(row.original.developer_name),
        meta: { headerTitle: 'Developer', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'state',
        header: ({ column }) => <DataGridColumnHeader title="State" column={column} />,
        size: 130,
        enableSorting: false,
        cell: ({ row }) => truncated(row.original.state),
        meta: { headerTitle: 'State', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'sales_agent_name',
        header: ({ column }) => <DataGridColumnHeader title="Sales agent" column={column} />,
        size: 170,
        enableSorting: false,
        cell: ({ row }) => truncated(row.original.sales_agent_name),
        meta: { headerTitle: 'Sales agent', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'possible_duplicates',
        header: ({ column }) => (
          <DataGridColumnHeader title="Possible duplicate" column={column} />
        ),
        size: 300,
        enableSorting: false,
        cell: ({ row }) =>
          row.original.possible_duplicates.length > 0 ? (
            <ProjectRegistrationDuplicates items={row.original.possible_duplicates} />
          ) : (
            '-'
          ),
        meta: { headerTitle: 'Possible duplicate', skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        id: 'status',
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        size: 120,
        enableSorting: false,
        cell: ({ row }) => (
          <span className={`${STATUS_PILL_BASE} ${statusPillClass(row.original.status)}`}>
            {REGISTRATION_STATUS_LABELS[row.original.status] ?? row.original.status}
          </span>
        ),
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-4 w-20" /> },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination?.total ?? 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
  });

  const filtersActiveCount = statusFilter !== 'pending' ? 1 : 0;

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination?.total ?? 0}
      isLoading={isLoading}
      error={error}
      onRetry={() => void refetch()}
      isPlaceholderData={isPlaceholderData}
      rowHref={rowHref}
      emptyMessage="No registrations"
      standardToolbar={false}
      tableLayout={{
        width: 'fixed',
        columnsResizable: true,
        columnsVisibility: true,
      }}
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
                placeholder="Search..."
                className="w-64"
              />
            }
            filters={{
              kind: 'custom',
              active: filtersActiveCount > 0,
              activeCount: filtersActiveCount,
              content: (
                <div className="space-y-4">
                  <div>
                    <Label>Status</Label>
                    <SearchableSelect
                      value={statusFilter}
                      onChange={(next) => setStatusFilter(next || 'pending')}
                      placeholder="Status"
                      triggerClassName="mt-1 w-full"
                      options={STATUS_OPTIONS}
                    />
                  </div>
                  {filtersActiveCount > 0 && (
                    <div className="flex justify-end">
                      <Button variant="ghost" size="sm" onClick={() => setStatusFilter('pending')}>
                        Clear filters
                      </Button>
                    </div>
                  )}
                </div>
              ),
            }}
            onRefresh={() => void refetch()}
            isRefreshing={isFetching && !isLoading}
          />
        </CardHeader>
        <CardTable>
          <DataGridTable />
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>
    </DataGrid>
  );
}
