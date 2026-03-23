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
import { usePackingLists } from '../hooks/usePackingLists';
import type { PackingList } from '../types/packingList.types';
import { formatDate } from '@/lib/helpers';
import PackingListDeleteDialog from './packing-list-delete-dialog';
import PackingListBulkDeleteDialog from './PackingListBulkDeleteDialog';

export default function PackingListsList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'created_at', desc: true },
  ]);
  const [searchQuery, setSearchQuery] = useState('');
  const [packingListToDelete, setPackingListToDelete] =
    useState<PackingList | null>(null);
  const [selectedPackingListIds, setSelectedPackingListIds] = useState<Set<string>>(new Set());
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);

  const { data, isLoading, refetch } = usePackingLists({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
  });

  const handleRowClick = (row: PackingList) => {
    const packingListId = row.id;
    router.push(`/procurement-management/packing-lists/${packingListId}`);
  };

  const pagePackingLists = data?.data ?? [];
  const isAllSelected = pagePackingLists.length > 0 && selectedPackingListIds.size === pagePackingLists.length;

  const toggleSelection = (id: string) => {
    setSelectedPackingListIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => {
    if (isAllSelected) {
      setSelectedPackingListIds(new Set());
    } else {
      setSelectedPackingListIds(new Set(pagePackingLists.map((p) => p.id)));
    }
  };

  const columns = useMemo<ColumnDef<PackingList>[]>(
    () => [
      {
        id: 'select',
        header: () => (
          <Checkbox
            checked={isAllSelected}
            onCheckedChange={selectAll}
            aria-label="Select all"
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            checked={selectedPackingListIds.has(row.original.id)}
            onCheckedChange={() => toggleSelection(row.original.id)}
            aria-label={`Select ${row.original.shipment_number ?? row.original.id}`}
            onClick={(e) => e.stopPropagation()}
          />
        ),
        size: 44,
        enableResizing: false,
      },
      {
        accessorKey: 'shipment_number',
        header: ({ column }) => (
          <DataGridColumnHeader title="Shipment Number" column={column} />
        ),
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'shipping_container_number',
        header: ({ column }) => (
          <DataGridColumnHeader title="Container Number" column={column} />
        ),
        cell: ({ row }) =>
          row.original.shipping_container_number || '-',
        size: 160,
        meta: { skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'supplier.supplier_name',
        header: ({ column }) => (
          <DataGridColumnHeader title="Supplier" column={column} />
        ),
        cell: ({ row }) => row.original.supplier?.supplier_name || '-',
        size: 200,
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'shipment_date',
        header: ({ column }) => (
          <DataGridColumnHeader title="Shipment Date" column={column} />
        ),
        cell: ({ row }) =>
          row.original.shipment_date
            ? formatDate(new Date(row.original.shipment_date))
            : '-',
        size: 120,
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'estimated_arrival_date',
        header: ({ column }) => (
          <DataGridColumnHeader title="Expected Arrival" column={column} />
        ),
        cell: ({ row }) =>
          row.original.estimated_arrival_date
            ? formatDate(new Date(row.original.estimated_arrival_date))
            : '-',
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'total_items_shipped',
        header: ({ column }) => (
          <DataGridColumnHeader title="Items" column={column} />
        ),
        cell: ({ row }) =>
          row.original.display_total_items ??
          row.original.total_items_shipped ??
          0,
        size: 100,
        meta: { skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: ({ row }) => (
          <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
            <Button
              mode="icon"
              variant="dim"
              size="sm"
              className="size-8"
              onClick={(e) => {
                e.stopPropagation();
                setPackingListToDelete(row.original);
              }}
              aria-label="Delete packing list"
            >
              <Trash2 className="size-4 text-destructive" />
            </Button>
            <ChevronRight className="text-muted-foreground/70 size-3.5" />
          </div>
        ),
        size: 80,
      },
    ],
    [isAllSelected, selectedPackingListIds],
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
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      onRowClick={handleRowClick}
    >
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
            <Input
              placeholder="Search by shipment or container number..."
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
            {selectedPackingListIds.size > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setBulkDeleteDialogOpen(true)}
                className="text-destructive hover:text-destructive"
              >
                <Trash2 className="size-4" />
                Bulk Delete ({selectedPackingListIds.size})
              </Button>
            )}
            <Button
              onClick={() =>
                router.push('/procurement-management/packing-lists/new')
              }
            >
              <Plus />
              Create Packing List
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
      {packingListToDelete && (
        <PackingListDeleteDialog
          open
          closeDialog={() => setPackingListToDelete(null)}
          packingList={packingListToDelete}
          onSuccess={() => refetch()}
        />
      )}
      <PackingListBulkDeleteDialog
        open={bulkDeleteDialogOpen}
        onOpenChange={(open) => {
          setBulkDeleteDialogOpen(open);
          if (!open) setSelectedPackingListIds(new Set());
        }}
        packingListIds={Array.from(selectedPackingListIds)}
        onSuccess={() => {
          setSelectedPackingListIds(new Set());
          refetch();
        }}
      />
    </DataGrid>
  );
}
