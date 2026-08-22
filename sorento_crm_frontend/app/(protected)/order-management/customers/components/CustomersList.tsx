'use client';

import { useEffect, useMemo, useState } from 'react';
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
import { Plus, Search, Upload, X, ChevronRight } from 'lucide-react';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
import { useImportJobDrawer } from '@/components/upload-activity';
import { useCustomers } from '../hooks/useCustomers';
import { buildDetailSearch } from '@/lib/listNavQuery';
import type { Customer } from '../types/customer.types';
import { CustomerImportDialog } from './CustomerImportDialog';
import {
  importCustomers,
  validateCustomerImport,
} from '../services/customerImportService';

export default function CustomersList() {
  const router = useRouter();
  const { notifyImportQueued } = useImportJobDrawer();
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const { data, isLoading, refetch, isFetching } = useCustomers({
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

  const handleRowClick = (row: Customer) => {
    const customerId = row.id;
    // Carry the active list query into the detail URL so its prev/next pager
    // walks the same filtered+sorted set.
    const search = buildDetailSearch({
      pageIndex: pagination.pageIndex,
      pageSize: pagination.pageSize,
      sorting,
      searchQuery,
    });
    const qs = search ? `?${search}` : '';
    router.push(`/order-management/customers/${customerId}${qs}`);
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
          <Badge variant={row.original.is_active ? 'success' : 'secondary'} appearance="ghost">
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
        cell: () => <ChevronRight className="text-muted-foreground/70 size-3.5" />,
        size: 40,
        enableHiding: false,
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

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      onRowClick={handleRowClick}
      tableLayout={{ columnsVisibility: true }}
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <div className="relative">
                <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                <Input
                  placeholder="Search customers..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="ps-9 w-64"
                />
                {searchQuery && (
                  <Button
                    mode="icon"
                    variant="dim"
                    className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                    onClick={() => setSearchQuery('')}
                  >
                    <X />
                  </Button>
                )}
              </div>
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
            primaryAction={
              <Button onClick={() => router.push('/order-management/customers/new')}>
                <Plus />
                Create Customer
              </Button>
            }
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
