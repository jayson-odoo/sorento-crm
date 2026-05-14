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
import { Plus, Search, X, ChevronRight, Columns3, Upload, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { useQueryClient } from '@tanstack/react-query';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { TemplateUploadDialog } from '@/components/template/TemplateUploadDialog';
import { LatestImportStatusPanel } from '@/components/import-jobs/LatestImportStatusPanel';
import { useWarehouses } from '../hooks/useWarehouses';
import { bulkImportWarehouses, validateWarehouseImport } from '../services/warehouseService';
import type { Warehouse } from '../types/warehouse.types';
import WarehouseBulkDeleteDialog from './WarehouseBulkDeleteDialog';

export default function WarehousesList() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const handleImportUpload = async (rows: Record<string, unknown>[]) => {
    await bulkImportWarehouses(rows);
    toast.success(
      'Import job queued successfully. Processing in background. Refresh shortly to see results.',
      {
        duration: 5000,
        action: {
          label: 'View Status',
          onClick: () => router.push('/system-management/import-jobs'),
        },
      },
    );
    queryClient.invalidateQueries({ queryKey: ['warehouses'] });
  };

  const { data, isLoading, refetch, isFetching } = useWarehouses({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
  });

  const toggleSelection = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const pageRowIds = (data?.data || []).map((r) => r.id);
  const isAllSelected = pageRowIds.length > 0 && pageRowIds.every((id) => selectedIds.has(id));
  const selectAllOnPage = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (isAllSelected) pageRowIds.forEach((id) => next.delete(id));
      else pageRowIds.forEach((id) => next.add(id));
      return next;
    });
  };

  const columns = useMemo<ColumnDef<Warehouse>[]>(
    () => [
      {
        id: 'select',
        header: () => (
          <Checkbox
            checked={isAllSelected}
            onCheckedChange={selectAllOnPage}
            aria-label="Select all"
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            checked={selectedIds.has(row.original.id)}
            onCheckedChange={() => toggleSelection(row.original.id)}
            aria-label={`Select ${row.original.warehouse_code}`}
            onClick={(e: React.MouseEvent) => e.stopPropagation()}
          />
        ),
        size: 44,
        enableResizing: false,
        enableSorting: false,
      },
      {
        accessorKey: 'warehouse_code',
        header: ({ column }) => <DataGridColumnHeader title="System Location" column={column} />,
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'warehouse_name',
        header: ({ column }) => <DataGridColumnHeader title="System Location Description" column={column} />,
        size: 240,
        cell: ({ row }) => row.original.warehouse_name || '-',
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'location',
        header: ({ column }) => <DataGridColumnHeader title="Warehouse" column={column} />,
        size: 200,
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'zones_count',
        header: ({ column }) => <DataGridColumnHeader title="Zones" column={column} />,
        size: 100,
        cell: ({ row }) => row.original.zones_count || 0,
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
        accessorKey: 'actions',
        header: '',
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push(`/inventory-management/warehouses/${row.original.id}`)}
          >
            <ChevronRight className="text-muted-foreground/70 size-3.5" />
          </Button>
        ),
        size: 40,
      },
    ],
    [isAllSelected, selectedIds, router],
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
  });

  return (
    <DataGrid table={table} recordCount={data?.pagination.total || 0} isLoading={isLoading}
      tableLayout={{ columnsVisibility: true }}
      onRefresh={() => void refetch()}
      isRefreshing={isFetching && !isLoading}
    >
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
            <Input
              placeholder="Search warehouses..."
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
            {selectedIds.size > 0 && (
              <Button
                variant="outline"
                className="text-destructive"
                onClick={() => setBulkDeleteDialogOpen(true)}
              >
                <Trash2 />
                Delete ({selectedIds.size})
              </Button>
            )}
            <DataGridColumnVisibility
              table={table}
              trigger={
                <Button variant="outline" size="sm" className="gap-1">
                  <Columns3 className="size-4" />
                  Columns
                </Button>
              }
            />
            <Button variant="outline" onClick={() => setUploadDialogOpen(true)}>
              <Upload />
              Import
            </Button>
            <Button onClick={() => router.push('/inventory-management/warehouses/new')}>
              <Plus />
              Create Warehouse
            </Button>
          </div>
        </CardHeader>
        <LatestImportStatusPanel jobType="warehouse_import" title="Latest warehouse import" className="mx-5 mb-2" />
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
      <TemplateUploadDialog
        open={uploadDialogOpen}
        onOpenChange={setUploadDialogOpen}
        onTest={async (rows) =>
          validateWarehouseImport(rows as Record<string, unknown>[]).then((r) => ({
            valid: r.valid,
            errors: r.errors,
            warnings: r.warnings.map((w) => {
              if (typeof w === 'string') return w;
              const row = w.row !== undefined ? `Row ${w.row}: ` : '';
              return `${row}${w.message ?? ''}`;
            }),
            summary: r.summary,
          }))
        }
        onUpload={async (rows) => handleImportUpload(rows as Record<string, unknown>[])}
      />
      <WarehouseBulkDeleteDialog
        open={bulkDeleteDialogOpen}
        onOpenChange={setBulkDeleteDialogOpen}
        warehouseIds={Array.from(selectedIds)}
        onSuccess={() => setSelectedIds(new Set())}
      />
    </DataGrid>
  );
}
