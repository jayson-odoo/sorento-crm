'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  type ColumnDef,
  type PaginationState,
  type SortingState,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
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
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useListStateFromUrl } from '@/hooks/useListStateFromUrl';
import { useResetPageOnFilterChange } from '@/hooks/useResetPageOnFilterChange';
import { useHasPermission, usePermissions } from '@/hooks/usePermissions';
import { buildDetailSearch } from '@/lib/listNavQuery';
import { formatDateInMalaysia } from '@/lib/helpers';
import { joinMulti, splitMulti } from '@/lib/list-filters/multiValue';
import { formatMoneyExact } from '@/app/(protected)/project-sales/_shared/lib/money';
import {
  SPARE_PART_CREATE_PERMISSION,
  SPARE_PART_REQUESTS_PATH,
  SPARE_PART_STATUS_OPTIONS,
  sparePartFilterStates,
  sparePartRequestStatusLabel,
  sparePartStateVariant,
} from '@/app/(protected)/project-sales/_shared/lib/sparePartRequest';
import { useSparePartRequests } from '@/app/(protected)/project-sales/_shared/hooks/useSparePartRequest';
import type { SparePartRequestListItem } from '@/app/(protected)/project-sales/_shared/services/sparePartRequestService';

const day = (value: string | null | undefined) => (value ? formatDateInMalaysia(value) : '-');

/** Column preferences key on a slug the reader holds (`/list-query/column-config`). */
function useListingKey(): string | null {
  const { permissionSet, isLoading } = usePermissions();
  if (isLoading) return null;
  const slug = [SPARE_PART_CREATE_PERMISSION, 'projects.projects.view'].find((s) =>
    permissionSet.has(s),
  );
  return slug ? `${slug}::spare_part_requests` : null;
}

/**
 * SPARE-PART-ORDER-REQUEST (hand-test round G3): the requests' own list. The server decides
 * which rows a reader gets (their own, the pending ones they can decide, every submitted one
 * for an admin); a row opens the request's record page.
 */
export function SparePartRequestsList() {
  const router = useRouter();
  const canCreate = useHasPermission(SPARE_PART_CREATE_PERMISSION);
  const listingKey = useListingKey();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: searchQuery,
    isSettling: searchSettling,
    reset: resetSearch,
  } = useDebouncedSearch();
  const [statusFilter, setStatusFilter] = useState('');

  useListStateFromUrl((state) => {
    setPagination({ pageIndex: state.pageIndex, pageSize: state.pageSize });
    setSorting(state.sorting);
    resetSearch(state.searchQuery);
    setStatusFilter(state.filters.status ?? '');
  });

  const states = useMemo(() => sparePartFilterStates(splitMulti(statusFilter)), [statusFilter]);
  const { data, isLoading, isPlaceholderData, refetch, isFetching, error } = useSparePartRequests({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    states,
  });

  useResetPageOnFilterChange(setPagination, [statusFilter, searchQuery]);

  const rowHref = (row: SparePartRequestListItem) => {
    const search = buildDetailSearch(
      { pageIndex: pagination.pageIndex, pageSize: pagination.pageSize, sorting, searchQuery },
      { status: statusFilter || undefined },
    );
    return `${SPARE_PART_REQUESTS_PATH}/${row.id}${search ? `?${search}` : ''}`;
  };

  const columns = useMemo<ColumnDef<SparePartRequestListItem>[]>(
    () => [
      {
        accessorKey: 'inquiry_no',
        header: ({ column }) => <DataGridColumnHeader title="Number" column={column} />,
        size: 150,
        cell: ({ row }) => (
          <span className="truncate font-medium tabular-nums" title={row.original.inquiry_no ?? ''}>
            {row.original.inquiry_no ?? '-'}
          </span>
        ),
        meta: { headerTitle: 'Number', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'state',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        size: 160,
        cell: ({ row }) => (
          <Badge variant={sparePartStateVariant(row.original.state)} appearance="light">
            {sparePartRequestStatusLabel(row.original.state)}
          </Badge>
        ),
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'requested_by_name',
        header: ({ column }) => <DataGridColumnHeader title="Requested by" column={column} />,
        size: 200,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.requested_by_name ?? ''}>
            {row.original.requested_by_name || '-'}
          </span>
        ),
        meta: { headerTitle: 'Requested by', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'needed_by',
        header: ({ column }) => <DataGridColumnHeader title="Needed by" column={column} />,
        size: 130,
        cell: ({ row }) => <span className="tabular-nums">{day(row.original.needed_by)}</span>,
        meta: { headerTitle: 'Needed by', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'line_count',
        header: ({ column }) => <DataGridColumnHeader title="Lines" column={column} />,
        size: 100,
        cell: ({ row }) => <span className="tabular-nums">{row.original.line_count}</span>,
        meta: { headerTitle: 'Lines', skeleton: <Skeleton className="h-4 w-8" /> },
      },
      {
        accessorKey: 'total',
        header: ({ column }) => <DataGridColumnHeader title="Total" column={column} />,
        size: 150,
        cell: ({ row }) => {
          const text =
            row.original.total == null
              ? '-'
              : formatMoneyExact(row.original.total, row.original.currency);
          return (
            <span className="truncate tabular-nums" title={text}>
              {text}
            </span>
          );
        },
        meta: { headerTitle: 'Total', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'submitted_at',
        header: ({ column }) => <DataGridColumnHeader title="Submitted" column={column} />,
        size: 130,
        cell: ({ row }) => <span className="tabular-nums">{day(row.original.submitted_at)}</span>,
        meta: { headerTitle: 'Submitted', skeleton: <Skeleton className="h-4 w-20" /> },
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

  const filtersActiveCount = statusFilter ? 1 : 0;

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination?.total ?? 0}
      isLoading={isLoading}
      error={error}
      onRetry={() => void refetch()}
      isPlaceholderData={isPlaceholderData}
      rowHref={rowHref}
      listingKey={listingKey}
      emptyMessage="No spare part requests yet"
      standardToolbar={false}
      tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
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
                    <SearchableMultiSelect
                      value={splitMulti(statusFilter)}
                      onChange={(v) => setStatusFilter(joinMulti(v))}
                      placeholder="Status"
                      triggerClassName="mt-1 w-full"
                      options={SPARE_PART_STATUS_OPTIONS}
                      clearable
                    />
                  </div>
                  {filtersActiveCount > 0 ? (
                    <div className="flex justify-end">
                      <Button variant="ghost" size="sm" onClick={() => setStatusFilter('')}>
                        Clear filters
                      </Button>
                    </div>
                  ) : null}
                </div>
              ),
            }}
            onRefresh={() => void refetch()}
            isRefreshing={isFetching && !isLoading}
            primaryAction={
              canCreate ? (
                <Button onClick={() => router.push(`${SPARE_PART_REQUESTS_PATH}/new`)}>
                  <Plus />
                  Create
                </Button>
              ) : undefined
            }
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

export default SparePartRequestsList;
