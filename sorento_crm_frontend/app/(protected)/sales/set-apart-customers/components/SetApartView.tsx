'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Skeleton } from '@/components/ui/skeleton';
import { Container } from '@/components/common/container';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { PageHeader } from '@/components/common/PageHeader';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useHasPermission } from '@/hooks/usePermissions';
import { useSetApartCustomers } from '../hooks/useSetApart';
import { SetApartRowActions } from '../actions';
import type { SetApartRow } from '../types/setApart.types';
import SetApartModal from './SetApartModal';

/**
 * Sales > Set-apart customers. A server-sorted, server-paged DataGrid; Add sits in the
 * header, Edit and Delete in each row's menu. Seeing the list needs `sales.reports.view`
 * (the route gate); changing it needs `sales.set_apart.edit`.
 */
export default function SetApartView() {
  const canEdit = useHasPermission('sales.set_apart.edit');
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<SetApartRow | null>(null);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const {
    value: searchQuery,
    setValue: setSearchQuery,
    debouncedValue: debouncedSearch,
    isSettling,
  } = useDebouncedSearch();

  const { data, isLoading, isFetching, isPlaceholderData, isError, error } = useSetApartCustomers({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery: debouncedSearch,
  });
  const rows = useMemo<SetApartRow[]>(() => data?.data ?? [], [data]);
  const total = data?.pagination.total ?? 0;

  const openAdd = () => {
    setEditing(null);
    setModalOpen(true);
  };
  const openEdit = (row: SetApartRow) => {
    setEditing(row);
    setModalOpen(true);
  };

  const addButton = (
    <Button variant="primary" onClick={openAdd}>
      <Plus className="size-4" />
      Add customer
    </Button>
  );

  const text = (value: string | null) =>
    value ? (
      <span className="block truncate" title={value}>
        {value}
      </span>
    ) : (
      <span className="text-muted-foreground">-</span>
    );

  const columns = useMemo<ColumnDef<SetApartRow>[]>(
    () => [
      {
        accessorKey: 'debtor_code',
        header: ({ column }) => <DataGridColumnHeader title="Debtor code" column={column} />,
        cell: ({ row }) => text(row.original.debtor_code),
        size: 160,
        meta: { headerTitle: 'Debtor code', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'customer_name',
        header: ({ column }) => <DataGridColumnHeader title="Customer" column={column} />,
        cell: ({ row }) => text(row.original.customer_name),
        size: 320,
        meta: { headerTitle: 'Customer', skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        accessorKey: 'from_month',
        header: ({ column }) => <DataGridColumnHeader title="From month" column={column} />,
        cell: ({ row }) => text(row.original.from_month),
        size: 140,
        meta: { headerTitle: 'From month', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'to_month',
        header: ({ column }) => <DataGridColumnHeader title="To month" column={column} />,
        cell: ({ row }) => text(row.original.to_month),
        size: 140,
        meta: { headerTitle: 'To month', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'actions',
        header: '',
        cell: ({ row }) => <SetApartRowActions row={row.original} onEdit={openEdit} />,
        size: 56,
        enableSorting: false,
        enableResizing: false,
        meta: { headerTitle: 'Actions' },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil(total / pagination.pageSize) || 1,
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: (updater) => {
      setSorting(updater);
      setPagination((prev) => ({ ...prev, pageIndex: 0 }));
    },
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const emptyMessage = debouncedSearch ? (
    'No set-apart customers match this search.'
  ) : (
    <div className="flex w-full flex-col items-center gap-1 py-6">
      <span className="text-sm font-medium">No set-apart customers yet</span>
      <span className="text-sm text-muted-foreground">Added customers appear here.</span>
    </div>
  );

  return (
    <>
      <Container>
        <PageHeader title="Set-apart customers" actions={canEdit ? addButton : undefined} />
      </Container>
      <Container>
        <div className="space-y-3">
          {isError ? (
            <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
              {error instanceof Error ? error.message : 'Failed to load set-apart customers.'}
            </div>
          ) : null}
          <DataGrid
            table={table}
            recordCount={total}
            isLoading={isLoading}
            isPlaceholderData={isPlaceholderData}
            listingKey="sales.reports.view::set-apart-customers"
            tableLayout={{ width: 'fixed', columnsResizable: true }}
            emptyMessage={emptyMessage}
          >
            <Card>
              <CardHeader className="flex flex-wrap items-center gap-3 py-3">
                <ListSearchInput
                  value={searchQuery}
                  onChange={(value) => {
                    setSearchQuery(value);
                    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
                  }}
                  isSettling={isSearchInFlight(isSettling, isFetching, debouncedSearch)}
                  placeholder="Search customers..."
                  className="w-full sm:w-64"
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
        </div>
      </Container>
      <SetApartModal open={modalOpen} onOpenChange={setModalOpen} row={editing} />
    </>
  );
}
