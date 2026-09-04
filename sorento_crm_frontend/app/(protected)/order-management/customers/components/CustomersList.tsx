'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  SortingState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Plus, Upload } from 'lucide-react';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
import { useImportJobDrawer } from '@/components/upload-activity';
import { useCustomers } from '../hooks/useCustomers';
import { buildDetailSearch } from '@/lib/listNavQuery';
import type { Customer } from '../types/customer.types';
import { CustomerRowActions } from '../actions';
import { CustomerImportDialog } from './CustomerImportDialog';
import {
  importCustomers,
  validateCustomerImport,
} from '../services/customerImportService';
import { useListStateFromUrl } from '@/hooks/useListStateFromUrl';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';

export default function CustomersList() {
  const router = useRouter();
  const { notifyImportQueued } = useImportJobDrawer();
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: searchQuery,
    isSettling: searchSettling,
    reset: resetSearch,
  } = useDebouncedSearch();
  const [statusFilter, setStatusFilter] = useState<string>('all');

  // Back hands the list its own query string back, and the pager keeps
  // rewriting it, so the list reads it (S3-01). One hook, every list.
  useListStateFromUrl((state) => {
    setPagination({ pageIndex: state.pageIndex, pageSize: state.pageSize });
    setSorting(state.sorting);
    resetSearch(state.searchQuery);
    setStatusFilter(state.filters.status ?? 'all');
  });
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const { data, isLoading, isPlaceholderData, refetch, isFetching } = useCustomers({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    status: statusFilter === 'all' ? undefined : statusFilter,
  });

  // Reset selection whenever the result set changes.
  useEffect(() => {
    setRowSelection({});
  }, [searchQuery, statusFilter, pagination.pageIndex, pagination.pageSize, sorting]);

  // A search brings the reader back to page 0 to see the matches; the mounted
  // guard keeps the URL-restored page from being clobbered on first render.
  const searchMounted = useRef(false);
  useEffect(() => {
    if (!searchMounted.current) {
      searchMounted.current = true;
      return;
    }
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [searchQuery]);

  // The whole row opens the record, carrying the list query the pager rebuilds
  // its key from - the status filter included, or the pager would page a wider
  // set than the user was looking at.
  const rowHref = (row: Customer) => {
    const search = buildDetailSearch(
      {
        pageIndex: pagination.pageIndex,
        pageSize: pagination.pageSize,
        sorting,
        searchQuery,
      },
      { status: statusFilter === 'all' ? undefined : statusFilter },
    );
    const qs = search ? `?${search}` : '';
    return `/order-management/customers/${row.id}${qs}`;
  };

  const columns = useMemo<ColumnDef<Customer>[]>(
    () => [
      buildSelectColumn<Customer>(),
      {
        accessorKey: 'customer_code',
        header: ({ column }) => <DataGridColumnHeader title="Customer Code" column={column} />,
        size: 150,
        meta: { headerTitle: 'Customer Code', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'customer_name',
        header: ({ column }) => <DataGridColumnHeader title="Customer Name" column={column} />,
        size: 250,
        meta: { headerTitle: 'Customer Name', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'email',
        header: ({ column }) => <DataGridColumnHeader title="Email" column={column} />,
        size: 200,
        meta: { headerTitle: 'Email', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'phone_number',
        header: ({ column }) => <DataGridColumnHeader title="Phone" column={column} />,
        size: 150,
        meta: { headerTitle: 'Phone', skeleton: <Skeleton className="h-4 w-24" /> },
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
        size: 100,
        meta: { headerTitle: 'Status' },
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: ({ row }) => <CustomerRowActions customer={row.original} />,
        size: 60,
        enableSorting: false,
        enableHiding: false,
        enableResizing: false,
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting, rowSelection },
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
  });

  // The one offer this listing makes, in both places it belongs: the
  // toolbar, and the empty state's next step (S5-06).
  const listPrimaryAction = (
    <Button onClick={() => router.push('/order-management/customers/new')}>
      <Plus />
      Create Customer
    </Button>
  );

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      isPlaceholderData={isPlaceholderData}
      rowHref={rowHref}
      tableLayout={{ columnsVisibility: true }}
      emptyAction={listPrimaryAction}
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
                placeholder="Search customers..."
                className="w-64"
              />
            }
            filters={{
              kind: 'custom',
              active: statusFilter !== 'all',
              activeCount: statusFilter !== 'all' ? 1 : 0,
              content: (
                <div className="space-y-4">
                  <div>
                    <Label>Status</Label>
                    <SearchableSelect
                      value={statusFilter}
                      onChange={(v) => {
                        setStatusFilter(v);
                        setPagination((p) => ({ ...p, pageIndex: 0 }));
                      }}
                      options={[
                        { value: 'all', label: 'All statuses' },
                        { value: 'active', label: 'Active' },
                        { value: 'inactive', label: 'Inactive' },
                      ]}
                      placeholder="All statuses"
                      triggerClassName="mt-1"
                    />
                  </div>
                  {statusFilter !== 'all' && (
                    <div className="flex justify-end">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setStatusFilter('all');
                          setPagination((p) => ({ ...p, pageIndex: 0 }));
                        }}
                      >
                        Clear filters
                      </Button>
                    </div>
                  )}
                </div>
              ),
            }}
            exportConfig={{ filename: 'customers_export.xlsx' }}
            onRefresh={() => void refetch()}
            isRefreshing={isFetching && !isLoading}
            secondaryActions={[
              {
                key: 'import',
                label: 'Import',
                icon: Upload,
                onClick: () => setImportDialogOpen(true),
              },
            ]}
            primaryAction={listPrimaryAction}
          />
        </CardHeader>
        <CustomerImportDialog
          open={importDialogOpen}
          onOpenChange={setImportDialogOpen}
          onTest={validateCustomerImport}
          onUpload={async (file) => {
            const queued = await importCustomers(file);
            // Opens the upload drawer and refetches the feed; the job then drives its
            // own 5s polling until terminal, so the user can leave the page.
            notifyImportQueued();
            void refetch();
            return queued;
          }}
        />
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
