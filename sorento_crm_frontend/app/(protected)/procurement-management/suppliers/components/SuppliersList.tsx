'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
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
import { ChevronDown, PencilLine, Plus } from 'lucide-react';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn, selectedRowIds } from '@/components/ui/data-grid-select-column';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { Skeleton } from '@/components/ui/skeleton';
import {
  BulkUpdateDialog,
  type BulkEditableField,
} from '@/components/common/BulkUpdateDialog';
import { useSuppliers } from '../hooks/useSuppliers';
import { bulkUpdateSuppliers } from '../services/supplierBulkUpdateService';
import type { Supplier } from '../types/supplier.types';
import type { ListQueryFilterGroup } from '@/lib/list-query/listQueryService';
import { buildDetailSearch, decodeAdvancedFilter, encodeAdvancedFilter } from '@/lib/listNavQuery';
import { SupplierRowActions } from '../actions';
import { useListStateFromUrl } from '@/hooks/useListStateFromUrl';

// Whitelist of bulk-editable fields for suppliers (the safety boundary - mirrors
// the backend registry in app/services/bulk_update_registry.py). Only these
// fields/values can be bulk-edited; every row still runs through the normal
// SupplierService.update_supplier path (validated + audit-trailed).
const SUPPLIER_BULK_FIELDS: BulkEditableField[] = [
  {
    key: 'is_active',
    label: 'Status',
    type: 'select',
    options: [
      { value: 'true', label: 'Active' },
      { value: 'false', label: 'Inactive' },
    ],
    helpText: 'Set the selected suppliers active or inactive.',
  },
];

export default function SuppliersList() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [bulkOpen, setBulkOpen] = useState(false);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: searchQuery,
    isSettling: searchSettling,
    reset: resetSearch,
  } = useDebouncedSearch();
  const [advancedFilter, setAdvancedFilter] = useState<ListQueryFilterGroup | null>(null);

  // Back hands the list its own query string back, and the pager keeps
  // rewriting it, so the list reads it (S3-01). One hook, every list.
  useListStateFromUrl((state) => {
    setPagination({ pageIndex: state.pageIndex, pageSize: state.pageSize });
    setSorting(state.sorting);
    resetSearch(state.searchQuery);
    setAdvancedFilter(
      decodeAdvancedFilter<ListQueryFilterGroup>(state.filters.advFilter),
    );
  });
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [advancedFilter, searchQuery]);

  const { data, isLoading, isFetching, isError, error } = useSuppliers({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    advancedFilter: advancedFilter ?? undefined,
  });

  // The whole row opens the record, carrying the list query the pager rebuilds
  // its key from.
  const rowHref = (row: Supplier) => {
    const search = buildDetailSearch(
      {
        pageIndex: pagination.pageIndex,
        pageSize: pagination.pageSize,
        sorting,
        searchQuery,
      },
      { advFilter: encodeAdvancedFilter(advancedFilter) },
    );
    return `/procurement-management/suppliers/${row.id}${search ? `?${search}` : ''}`;
  };

  const columns = useMemo<ColumnDef<Supplier>[]>(
    () => [
      buildSelectColumn<Supplier>(),
      {
        accessorKey: 'supplier_code',
        header: ({ column }) => <DataGridColumnHeader title="Supplier Code" column={column} />,
        size: 150,
        meta: { headerTitle: 'Supplier Code', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'supplier_name',
        header: ({ column }) => <DataGridColumnHeader title="Supplier Name" column={column} />,
        size: 250,
        meta: { headerTitle: 'Supplier Name', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'contact_name',
        header: ({ column }) => <DataGridColumnHeader title="Contact Person" column={column} />,
        size: 200,
        meta: { headerTitle: 'Contact Person', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'phone_number',
        header: ({ column }) => <DataGridColumnHeader title="Phone" column={column} />,
        size: 150,
        meta: { headerTitle: 'Phone', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'email',
        header: ({ column }) => <DataGridColumnHeader title="Email" column={column} />,
        size: 200,
        meta: { headerTitle: 'Email', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'is_active',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => {
          const isActive = row.original.is_active;
          return (
            <Badge
              variant={isActive ? 'success' : 'secondary'}
            >
              <BadgeDot />
              {isActive ? 'Active' : 'Inactive'}
            </Badge>
          );
        },
        size: 100,
        meta: { headerTitle: 'Status' },
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: ({ row }) => <SupplierRowActions supplier={row.original} />,
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

  const selectedIds = selectedRowIds(table);

  const handleBulkApply = async (fieldKey: string, value: string) => {
    const result = await bulkUpdateSuppliers(selectedIds, fieldKey, value);
    // Refetch the list so updated rows reflect the change, and drop the selection.
    await queryClient.invalidateQueries({ queryKey: ['suppliers'] });
    setRowSelection({});
    toast.success(
      `Bulk update applied - ${result.updated} updated${
        result.skipped.length ? `, ${result.skipped.length} skipped` : ''
      }.`,
    );
    return result;
  };

  // The one offer this listing makes, in both places it belongs: the
  // toolbar, and the empty state's next step (S5-06).
  const listPrimaryAction = (
    <Button onClick={() => router.push('/procurement-management/suppliers/new')}>
      <Plus />
      Create Supplier
    </Button>
  );

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      rowHref={rowHref}
      standardToolbar={false}
      tableLayout={{ columnsVisibility: true }}
      emptyAction={listPrimaryAction}
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            bulkActionsSlot={() => (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" className="gap-1.5">
                    Action
                    <ChevronDown className="size-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                  <DropdownMenuItem onClick={() => setBulkOpen(true)}>
                    <PencilLine className="size-4 me-2" /> Bulk update…
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
            searchSlot={
              <ListSearchInput
                value={searchInput}
                onChange={setSearchInput}
                isSettling={isSearchInFlight(searchSettling, isFetching, searchQuery)}
                placeholder="Search suppliers..."
                className="w-64"
              />
            }
            filters={{
              kind: 'listQuery',
              resourceKey: 'suppliers',
              getPayload: () => ({
                filter: advancedFilter ?? undefined,
                quick_search: searchQuery || undefined,
              }),
              advancedFilter,
              onApply: setAdvancedFilter,
            }}
            exportConfig={{
              kind: 'listQuery',
              resourceKey: 'suppliers',
              filename: 'suppliers_export.xlsx',
              getPayload: () => ({
                filter: advancedFilter ?? undefined,
                quick_search: searchQuery || undefined,
              }),
            }}
            primaryAction={listPrimaryAction}
          />
        </CardHeader>
        {isError ? (
          <div className="px-5 pb-2 text-sm text-destructive">
            {error instanceof Error ? error.message : 'Failed to load suppliers'}
          </div>
        ) : null}
        <CardTable>
          <DataGridTable />
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>

      <BulkUpdateDialog
        open={bulkOpen}
        onOpenChange={setBulkOpen}
        selectedCount={selectedIds.length}
        fields={SUPPLIER_BULK_FIELDS}
        onApply={handleBulkApply}
      />
    </DataGrid>
  );
}
