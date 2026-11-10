'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Skeleton } from '@/components/ui/skeleton';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { usePaymentTermList } from '../hooks/usePaymentTermList';
import type { PaymentTermRow } from '../services/paymentTermListService';

/** The AutoCount payment terms the ESB syncs, read-only: one line per term. */
export default function PaymentTermList() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'term_code', desc: false }]);
  const {
    value: searchInputValue,
    setValue: setSearchInputValue,
    debouncedValue: searchQuery,
    isSettling: searchSettling,
  } = useDebouncedSearch();

  const { data, isLoading, isPlaceholderData, refetch, isFetching, error } = usePaymentTermList({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
  });

  const columns = useMemo<ColumnDef<PaymentTermRow>[]>(
    () => [
      {
        accessorKey: 'term_code',
        header: ({ column }) => <DataGridColumnHeader title="Term" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.term_code}>
            {row.original.term_code}
          </span>
        ),
        size: 280,
        meta: { headerTitle: 'Term', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'term_rule',
        header: ({ column }) => <DataGridColumnHeader title="Rule" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.term_rule ?? ''}>
            {row.original.term_rule ?? ''}
          </span>
        ),
        size: 220,
        meta: { headerTitle: 'Rule', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'company_code',
        header: ({ column }) => <DataGridColumnHeader title="Company" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.company_code}>
            {row.original.company_code}
          </span>
        ),
        size: 120,
        meta: { headerTitle: 'Company' },
      },
      {
        accessorKey: 'is_active',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <Badge variant={row.original.is_active ? 'success' : 'secondary'}>
            <BadgeDot />
            {row.original.is_active ? 'Active' : 'Inactive'}
          </Badge>
        ),
        size: 120,
        meta: { headerTitle: 'Status' },
      },
    ],
    [],
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
    columnResizeMode: 'onChange',
  });

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      error={error}
      onRetry={() => void refetch()}
      isPlaceholderData={isPlaceholderData}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      emptyMessage="No payment terms synced yet"
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <ListSearchInput
                value={searchInputValue}
                onChange={setSearchInputValue}
                isSettling={isSearchInFlight(searchSettling, isFetching, searchQuery)}
                placeholder="Search payment terms..."
                className="w-64"
              />
            }
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
