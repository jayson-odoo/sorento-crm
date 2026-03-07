'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Plus, Search, X, ChevronRight, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid, DataGridApiResponse } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { useForms } from '../hooks/useForms';
import type { Form } from '../types/form.types';
import { formatDate } from '@/lib/helpers';
import FormBulkDeleteDialog from './FormBulkDeleteDialog';

export default function FormsList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'updated_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedFormIds, setSelectedFormIds] = useState<Set<string>>(new Set());
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);

  const { data, isLoading } = useForms({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
  });

  const handleRowClick = (row: Form) => {
    const formId = row.id;
    router.push(`/forms-management/forms/${formId}`);
  };

  const toggleFormSelection = (formId: string) => {
    setSelectedFormIds((prev) => {
      const next = new Set(prev);
      if (next.has(formId)) next.delete(formId);
      else next.add(formId);
      return next;
    });
  };

  const selectAllForms = () => {
    const pageForms = data?.data ?? [];
    if (selectedFormIds.size === pageForms.length) {
      setSelectedFormIds(new Set());
    } else {
      setSelectedFormIds(new Set(pageForms.map((f) => f.id)));
    }
  };

  const pageForms = data?.data ?? [];
  const isAllSelected = pageForms.length > 0 && selectedFormIds.size === pageForms.length;

  const columns = useMemo<ColumnDef<Form>[]>(
    () => [
      {
        id: 'select',
        header: () => (
          <Checkbox
            checked={isAllSelected}
            onCheckedChange={selectAllForms}
            aria-label="Select all"
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            checked={selectedFormIds.has(row.original.id)}
            onCheckedChange={() => toggleFormSelection(row.original.id)}
            aria-label={`Select ${row.original.code}`}
            onClick={(e) => e.stopPropagation()}
          />
        ),
        size: 44,
        enableResizing: false,
      },
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
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
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
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
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
        meta: { skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'language',
        header: ({ column }) => <DataGridColumnHeader title="Language" column={column} />,
        size: 100,
      },
      {
        accessorKey: 'version',
        header: ({ column }) => <DataGridColumnHeader title="Version" column={column} />,
        size: 100,
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
      },
      {
        accessorKey: 'updated_at',
        header: ({ column }) => <DataGridColumnHeader title="Last Updated" column={column} />,
        cell: ({ row }) => formatDate(new Date(row.original.updated_at)),
        size: 150,
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: () => <ChevronRight className="text-muted-foreground/70 size-3.5" />,
        size: 40,
      },
    ],
    [selectedFormIds, isAllSelected],
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
    enableColumnResizing: true,
  });

  return (
    <DataGrid 
      table={table} 
      recordCount={data?.pagination.total || 0} 
      isLoading={isLoading}
      onRowClick={handleRowClick}
      tableLayout={{
        columnsResizable: true,
      }}
    >
      <Card>
        <CardHeader className="flex-row items-center justify-between">
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
          <div className="flex items-center gap-2">
            {selectedFormIds.size > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setBulkDeleteDialogOpen(true)}
                className="text-destructive hover:text-destructive"
              >
                <Trash2 className="size-4" />
                Bulk Delete ({selectedFormIds.size})
              </Button>
            )}
            <Button onClick={() => router.push('/forms-management/forms/new')}>
              <Plus />
              Create Form
            </Button>
          </div>
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
        onOpenChange={(open) => {
          setBulkDeleteDialogOpen(open);
          if (!open) setSelectedFormIds(new Set());
        }}
        formIds={Array.from(selectedFormIds)}
        onSuccess={() => setSelectedFormIds(new Set())}
      />
    </DataGrid>
  );
}
