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
import { ChevronRight, Plus, Search, X } from 'lucide-react';
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
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { useSuppliers } from '../hooks/useSuppliers';
import type { Supplier } from '../types/supplier.types';
import type { ListQueryFilterGroup } from '@/lib/list-query/listQueryService';
import { buildDetailSearch } from '@/lib/listNavQuery';

export default function SuppliersList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [advancedFilter, setAdvancedFilter] = useState<ListQueryFilterGroup | null>(null);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [advancedFilter]);

  const { data, isLoading, isError, error } = useSuppliers({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    advancedFilter: advancedFilter ?? undefined,
  });

  const handleRowClick = (row: Supplier) => {
    const supplierId = row.id;
    // Carry the active list query (search/sort) into the detail URL so the detail
    // page's prev/next pager walks the same filtered+sorted set.
    const search = buildDetailSearch({
      pageIndex: pagination.pageIndex,
      pageSize: pagination.pageSize,
      sorting,
      searchQuery,
    });
    router.push(
      `/procurement-management/suppliers/${supplierId}${search ? `?${search}` : ''}`,
    );
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
              appearance="ghost"
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
      standardToolbar={false}
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
                  placeholder="Search suppliers..."
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
            primaryAction={
              <Button onClick={() => router.push('/procurement-management/suppliers/new')}>
                <Plus />
                Create Supplier
              </Button>
            }
          />
        </CardHeader>
        {isError ? (
          <div className="px-5 pb-2 text-sm text-destructive">
            {error instanceof Error ? error.message : 'Failed to load suppliers'}
          </div>
        ) : null}
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
