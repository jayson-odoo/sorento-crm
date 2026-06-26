'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { buildDetailSearch } from '@/lib/listNavQuery';
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
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn, selectedRowIds } from '@/components/ui/data-grid-select-column';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { usePackingLists } from '../hooks/usePackingLists';
import type { PackingList } from '../types/packingList.types';
import { formatDate, formatDateTimeInMalaysia } from '@/lib/helpers';
import { formatStatusLabel, getStatusBadgeVariant } from '@/lib/status-badge';
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
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);

  const { data, isLoading, refetch, isFetching } = usePackingLists({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
  });

  const handleRowClick = (row: PackingList) => {
    const packingListId = row.id;
    // Carry the active list query into the detail URL so its prev/next pager
    // walks the same filtered+sorted set.
    const search = buildDetailSearch({
      pageIndex: pagination.pageIndex,
      pageSize: pagination.pageSize,
      sorting,
      searchQuery,
    });
    const qs = search ? `?${search}` : '';
    router.push(`/procurement-management/packing-lists/${packingListId}${qs}`);
  };

  const columns = useMemo<ColumnDef<PackingList>[]>(
    () => [
      buildSelectColumn<PackingList>(),
      {
        accessorKey: 'shipment_number',
        header: ({ column }) => (
          <DataGridColumnHeader title="Shipment Number" column={column} />
        ),
        cell: ({ row }) => row.original.shipment_number || '-',
        size: 150,
        meta: { headerTitle: 'Shipment Number', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'shipping_container_number',
        header: ({ column }) => (
          <DataGridColumnHeader title="Container Number" column={column} />
        ),
        cell: ({ row }) =>
          row.original.shipping_container_number || '-',
        size: 160,
        meta: { headerTitle: 'Container Number', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'supplier.supplier_name',
        header: ({ column }) => (
          <DataGridColumnHeader title="Supplier" column={column} />
        ),
        cell: ({ row }) => row.original.supplier?.supplier_name || '-',
        size: 200,
        meta: { headerTitle: 'Supplier', skeleton: <Skeleton className="h-4 w-32" /> },
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
        meta: { headerTitle: 'Shipment Date', skeleton: <Skeleton className="h-4 w-20" /> },
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
        meta: { headerTitle: 'Expected Arrival', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'shipment_status',
        header: ({ column }) => (
          <DataGridColumnHeader title="Status" column={column} />
        ),
        cell: ({ row }) => {
          const status = row.original.shipment_status;
          return (
            <Badge variant={getStatusBadgeVariant(status)}>
              {formatStatusLabel(status)}
            </Badge>
          );
        },
        size: 130,
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-4 w-20" /> },
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
        meta: { headerTitle: 'Items', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'created_at',
        header: ({ column }) => (
          <DataGridColumnHeader title="Created At" column={column} />
        ),
        cell: ({ row }) => formatDateTimeInMalaysia(row.original.created_at),
        size: 120,
        meta: { headerTitle: 'Created At', skeleton: <Skeleton className="h-4 w-20" /> },
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
            }
            exportConfig={{ filename: 'packing_lists_export.xlsx' }}
            onRefresh={() => void refetch()}
            isRefreshing={isFetching && !isLoading}
            primaryAction={
              <Button
                onClick={() =>
                  router.push('/procurement-management/packing-lists/new')
                }
              >
                <Plus />
                Create Packing List
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
          if (!open) setRowSelection({});
        }}
        packingListIds={selectedRowIds(table)}
        onSuccess={() => {
          setRowSelection({});
          refetch();
        }}
      />
    </DataGrid>
  );
}
