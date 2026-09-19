'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Skeleton } from '@/components/ui/skeleton';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { usePullRows } from '../hooks/useAutocountPull';
import type {
  AutocountPullEntity,
  AutocountPullExcelRow,
  ProductExcelRow,
  StockExcelRow,
} from '../types/autocountPull.types';

export interface PullExcelViewTabProps {
  jobId: string;
  entity: AutocountPullEntity;
}

const PRODUCT_COLUMNS: ColumnDef<AutocountPullExcelRow>[] = [
  {
    id: 'item_code',
    header: ({ column }) => <DataGridColumnHeader title="Item Code" column={column} />,
    cell: ({ row }) => (
      <span className="block truncate" title={row.original.item_code}>
        {row.original.item_code}
      </span>
    ),
    size: 140,
    meta: { headerTitle: 'Item Code', skeleton: <Skeleton className="h-4 w-20" /> },
  },
  {
    id: 'description',
    header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
    cell: ({ row }) => {
      const value = (row.original as ProductExcelRow).description;
      return (
        <span className="block truncate" title={value}>
          {value}
        </span>
      );
    },
    size: 320,
    meta: { headerTitle: 'Description', skeleton: <Skeleton className="h-4 w-48" /> },
  },
  {
    id: 'desc_2',
    header: ({ column }) => <DataGridColumnHeader title="Desc 2" column={column} />,
    cell: ({ row }) => {
      const value = (row.original as ProductExcelRow).desc_2 || '-';
      return (
        <span className="block truncate" title={value}>
          {value}
        </span>
      );
    },
    size: 220,
    meta: { headerTitle: 'Desc 2', skeleton: <Skeleton className="h-4 w-32" /> },
  },
  {
    id: 'item_group',
    header: ({ column }) => <DataGridColumnHeader title="Item Group" column={column} />,
    cell: ({ row }) => {
      const value = (row.original as ProductExcelRow).item_group || '-';
      return (
        <span className="block truncate" title={value}>
          {value}
        </span>
      );
    },
    size: 130,
    meta: { headerTitle: 'Item Group', skeleton: <Skeleton className="h-4 w-20" /> },
  },
  {
    id: 'item_brand',
    header: ({ column }) => <DataGridColumnHeader title="Item Brand" column={column} />,
    cell: ({ row }) => {
      const value = (row.original as ProductExcelRow).item_brand || '-';
      return (
        <span className="block truncate" title={value}>
          {value}
        </span>
      );
    },
    size: 130,
    meta: { headerTitle: 'Item Brand', skeleton: <Skeleton className="h-4 w-20" /> },
  },
  {
    id: 'price',
    header: ({ column }) => <DataGridColumnHeader title="Price" column={column} />,
    cell: ({ row }) => (
      <span className="tabular-nums">{(row.original as ProductExcelRow).price.toFixed(2)}</span>
    ),
    size: 100,
    meta: { headerTitle: 'Price', skeleton: <Skeleton className="h-4 w-16" /> },
  },
  {
    id: 'is_active',
    header: ({ column }) => <DataGridColumnHeader title="Is Active" column={column} />,
    cell: ({ row }) => <span>{(row.original as ProductExcelRow).is_active ? 'T' : 'F'}</span>,
    size: 90,
    meta: { headerTitle: 'Is Active', skeleton: <Skeleton className="h-4 w-8" /> },
  },
];

const STOCK_COLUMNS: ColumnDef<AutocountPullExcelRow>[] = [
  {
    id: 'item_code',
    header: ({ column }) => <DataGridColumnHeader title="Item Code" column={column} />,
    cell: ({ row }) => (
      <span className="block truncate" title={row.original.item_code}>
        {row.original.item_code}
      </span>
    ),
    size: 160,
    meta: { headerTitle: 'Item Code', skeleton: <Skeleton className="h-4 w-24" /> },
  },
  {
    id: 'item_description',
    header: ({ column }) => <DataGridColumnHeader title="Item Description" column={column} />,
    cell: ({ row }) => {
      const value = (row.original as StockExcelRow).item_description;
      return (
        <span className="block truncate" title={value}>
          {value}
        </span>
      );
    },
    size: 360,
    meta: { headerTitle: 'Item Description', skeleton: <Skeleton className="h-4 w-56" /> },
  },
  {
    id: 'location',
    header: ({ column }) => <DataGridColumnHeader title="Location" column={column} />,
    cell: ({ row }) => {
      const value = (row.original as StockExcelRow).location;
      return (
        <span className="block truncate" title={value}>
          {value}
        </span>
      );
    },
    size: 130,
    meta: { headerTitle: 'Location', skeleton: <Skeleton className="h-4 w-16" /> },
  },
  {
    id: 'on_hand_qty',
    header: ({ column }) => <DataGridColumnHeader title="On Hand Qty" column={column} />,
    cell: ({ row }) => (
      <span className="tabular-nums">
        {(row.original as StockExcelRow).on_hand_qty.toLocaleString()}
      </span>
    ),
    size: 120,
    meta: { headerTitle: 'On Hand Qty', skeleton: <Skeleton className="h-4 w-16" /> },
  },
];

/**
 * The whole pull laid out exactly like the manual template - same columns, same order, so it
 * can be read side by side with the macro workbook (AC-RV-3/4). Server-style paging + search,
 * fixed/resizable layout per the DataGrid listing contract.
 */
export function PullExcelViewTab({ jobId, entity }: PullExcelViewTabProps) {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: search,
    isSettling: searchSettling,
  } = useDebouncedSearch();

  const query = { pageIndex: pagination.pageIndex, pageSize: pagination.pageSize, query: search || undefined };
  const { data, isLoading, isPlaceholderData, isFetching, isError, error } = usePullRows(jobId, query);

  const columns = useMemo(() => (entity === 'products' ? PRODUCT_COLUMNS : STOCK_COLUMNS), [entity]);
  const total = data?.pagination?.total ?? 0;

  const table = useReactTable({
    columns,
    data: data?.data ?? [],
    pageCount: Math.ceil(total / pagination.pageSize) || 0,
    getRowId: (row) => row.item_code + ('location' in row ? `-${row.location}` : ''),
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    columnResizeMode: 'onChange',
  });

  return (
    <DataGrid
      table={table}
      recordCount={total}
      isLoading={isLoading}
      isPlaceholderData={isPlaceholderData}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
    >
      <Card>
        <CardHeader className="block space-y-3">
          <div className="w-full sm:w-80">
            <ListSearchInput
              value={searchInput}
              onChange={setSearchInput}
              isSettling={isSearchInFlight(searchSettling, isFetching, search)}
              placeholder="Search by item code…"
              className="w-full"
            />
          </div>
        </CardHeader>
        <CardTable>
          {isError ? (
            <div className="px-6 py-10 text-center text-sm text-destructive">
              {error instanceof Error ? error.message : 'Failed to load the pull rows'}
            </div>
          ) : !isLoading && total === 0 ? (
            <div className="px-6 py-10 text-center text-sm text-muted-foreground">
              {search ? 'No rows match that search.' : 'Nothing to show yet.'}
            </div>
          ) : (
            <DataGridTable />
          )}
        </CardTable>
        {total > 0 && (
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        )}
      </Card>
    </DataGrid>
  );
}

export default PullExcelViewTab;
