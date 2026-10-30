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
import { Plus, Trash2 } from 'lucide-react';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Skeleton } from '@/components/ui/skeleton';
import { useItemClasses } from '../hooks/useItemClasses';
import type { ItemClass } from '../types/item-class.types';
import { useDeferredRowAction, useRowPending } from '@/hooks/useDeferredRowAction';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import ItemClassFormDialog from './ItemClassFormDialog';

export default function ItemClassList() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'item_class_name', desc: false },
  ]);
  const {
    value: searchInputValue,
    setValue: setSearchInputValue,
    debouncedValue: searchQuery,
    isSettling: searchSettling,
  } = useDebouncedSearch();
  const [formOpen, setFormOpen] = useState(false);

  // Delete asks nothing (D7): the row dims and a toast counts down with Cancel. A class a
  // contact is limited to is refused by the server (409) as the toast's own error.
  const deletion = useDeferredRowAction({
    actionKey: 'item_class.delete',
    entityType: 'item_class',
    successMessage: 'Item class deleted',
    invalidateKeys: [['item-classes'], ['item-class-select']],
  });
  const rowPending = useRowPending<ItemClass>('item_class');

  const { data, isLoading, isPlaceholderData, refetch, isFetching, error } = useItemClasses({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
  });

  const columns = useMemo<ColumnDef<ItemClass>[]>(
    () => [
      {
        accessorKey: 'item_class_code',
        header: ({ column }) => <DataGridColumnHeader title="Code" column={column} />,
        cell: ({ row }) => (
          <span
            className="block truncate font-mono text-xs"
            title={row.original.item_class_code}
          >
            {row.original.item_class_code}
          </span>
        ),
        size: 140,
        meta: { headerTitle: 'Code', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'item_class_name',
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.item_class_name}>
            {row.original.item_class_name}
          </span>
        ),
        size: 280,
        meta: { headerTitle: 'Name', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'product_count',
        header: () => <span>Products</span>,
        cell: ({ row }) => <span>{row.original.product_count}</span>,
        size: 110,
        enableSorting: false,
        meta: { headerTitle: 'Products' },
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
      {
        id: 'actions',
        header: '',
        cell: ({ row }) => (
          <div className="flex items-center justify-end gap-1">
            <Button
              mode="icon"
              variant="ghost"
              aria-label={`Delete ${row.original.item_class_name}`}
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                deletion.run({ id: row.original.id, subject: row.original.item_class_name });
              }}
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        ),
        size: 60,
        enableHiding: false,
        enableResizing: false,
      },
    ],
    [deletion],
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

  const listPrimaryAction = (
    <Button onClick={() => setFormOpen(true)}>
      <Plus />
      Add Item Class
    </Button>
  );

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      error={error}
      onRetry={() => void refetch()}
      isPlaceholderData={isPlaceholderData}
      // The row opens the record, where view and edit are the same layout. Add stays a modal.
      rowHref={(row) => `/master-data-management/item-classes/${row.id}`}
      rowPending={rowPending}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      emptyMessage="No item classes yet"
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
                placeholder="Search item classes..."
                className="w-64"
              />
            }
            onRefresh={() => void refetch()}
            isRefreshing={isFetching && !isLoading}
            primaryAction={listPrimaryAction}
          />
        </CardHeader>
        <CardTable>
          <DataGridTable />
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>

      <ItemClassFormDialog open={formOpen} onOpenChange={setFormOpen} />
    </DataGrid>
  );
}
