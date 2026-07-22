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
import { ChevronRight, Plus, Search, Trash2, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import LookupBoundLabel from '@/components/common/LookupBoundLabel';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn, selectedRowIds } from '@/components/ui/data-grid-select-column';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
import { useForms } from '../hooks/useForms';
import type { Form } from '../types/form.types';
import { formatDate } from '@/lib/helpers';
import { buildDetailSearch } from '@/lib/listNavQuery';
import FormBulkDeleteDialog from './FormBulkDeleteDialog';

export default function FormsList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'updated_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);

  useEffect(() => {
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  }, [statusFilter]);

  const { data, isLoading, refetch, isFetching } = useForms({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    status: statusFilter !== 'all' ? statusFilter : undefined,
  });

  const handleRowClick = (row: Form) => {
    const formId = row.id;
    // Carry the active list query into the detail URL so its prev/next pager
    // walks the same filtered+sorted set.
    const search = buildDetailSearch(
      {
        pageIndex: pagination.pageIndex,
        pageSize: pagination.pageSize,
        sorting,
        searchQuery,
      },
      {
        status: statusFilter !== 'all' ? statusFilter : undefined,
      },
    );
    const qs = search ? `?${search}` : '';
    router.push(`/forms-management/forms/${formId}${qs}`);
  };

  const columns = useMemo<ColumnDef<Form>[]>(
    () => [
      buildSelectColumn<Form>(),
      {
        accessorKey: 'code',
        header: ({ column }) => <DataGridColumnHeader title="Form Code" column={column} />,
        cell: ({ row }) => (
          <div className="truncate" title={row.original.code}>
            {row.original.code}
          </div>
        ),
        size: 180,
        minSize: 120,
        meta: { headerTitle: 'Form Code', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Form Name" column={column} />,
        cell: ({ row }) => (
          <div className="truncate" title={row.original.name}>
            {row.original.name}
          </div>
        ),
        size: 250,
        minSize: 150,
        meta: { headerTitle: 'Form Name', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'form_type',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        cell: ({ row }) => (
          <Badge variant="outline" appearance="ghost" className="font-normal">
            <LookupBoundLabel
              table="forms"
              column="form_type"
              value={row.original.form_type || 'marketing'}
            />
          </Badge>
        ),
        size: 110,
        minSize: 90,
        meta: { headerTitle: 'Type', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'purpose',
        header: ({ column }) => <DataGridColumnHeader title="Purpose" column={column} />,
        cell: ({ row }) => {
          const purpose = row.original.purpose;
          if (!purpose || purpose.trim() === '') {
            return <span className="text-muted-foreground">-</span>;
          }
          return (
            <div className="truncate" title={purpose}>
              {purpose}
            </div>
          );
        },
        size: 200,
        minSize: 120,
        meta: { headerTitle: 'Purpose', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'language',
        header: ({ column }) => <DataGridColumnHeader title="Language" column={column} />,
        size: 100,
        meta: { headerTitle: 'Language' },
      },
      {
        accessorKey: 'version',
        header: ({ column }) => <DataGridColumnHeader title="Version" column={column} />,
        size: 100,
        meta: { headerTitle: 'Version' },
      },
      {
        accessorKey: 'is_active',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <Badge variant={row.original.is_active ? 'success' : 'secondary'} appearance="ghost">
            {row.original.is_active ? 'Active' : 'Inactive'}
          </Badge>
        ),
        size: 100,
        meta: { headerTitle: 'Status' },
      },
      {
        accessorKey: 'updated_at',
        header: ({ column }) => <DataGridColumnHeader title="Last Updated" column={column} />,
        cell: ({ row }) => formatDate(new Date(row.original.updated_at)),
        size: 150,
        meta: { headerTitle: 'Last Updated' },
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
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      onRowClick={handleRowClick}
      standardToolbar={false}
      tableLayout={{ columnsVisibility: true, columnsResizable: true }}
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <div className="relative">
                <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                <Input
                  placeholder="Search forms..."
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
                      onChange={setStatusFilter}
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
                      <Button variant="ghost" size="sm" onClick={() => setStatusFilter('all')}>
                        Clear filters
                      </Button>
                    </div>
                  )}
                </div>
              ),
            }}
            exportConfig={{ filename: 'forms_export.xlsx' }}
            onRefresh={() => void refetch()}
            isRefreshing={isFetching && !isLoading}
            primaryAction={
              <Button onClick={() => router.push('/forms-management/forms/new')}>
                <Plus />
                Create Form
              </Button>
            }
            bulkActions={[
              {
                key: 'delete',
                label: 'Delete',
                icon: Trash2,
                destructive: true,
                onClick: () => setBulkDeleteDialogOpen(true),
              },
            ]}
          />
        </CardHeader>
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
      <FormBulkDeleteDialog
        open={bulkDeleteDialogOpen}
        onOpenChange={setBulkDeleteDialogOpen}
        formIds={selectedRowIds(table)}
        onSuccess={() => setRowSelection({})}
      />
    </DataGrid>
  );
}
