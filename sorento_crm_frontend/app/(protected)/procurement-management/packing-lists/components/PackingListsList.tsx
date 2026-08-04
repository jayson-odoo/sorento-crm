'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { buildDetailSearch } from '@/lib/listNavQuery';
import {
  ColumnDef,
  PaginationState,
  RowSelectionState,
  SortingState,
  VisibilityState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { ChevronRight, Plus, RefreshCw, Search, Trash2, Upload, X } from 'lucide-react';
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
import ContainerStatusImportDialog from './ContainerStatusImportDialog';

export default function PackingListsList() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [importDialogOpen, setImportDialogOpen] = useState(false);

  // The "no container status imported yet" empty state on a packing list detail page
  // links back here with ?import=container-status so the CTA lands on the upload
  // itself rather than dead-ending on the list.
  useEffect(() => {
    if (searchParams.get('import') === 'container-status') setImportDialogOpen(true);
  }, [searchParams]);
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'created_at', desc: true },
  ]);
  const [searchQuery, setSearchQuery] = useState('');
  /**
   * Clearance columns are OFF by default. There are 17 of them; showing them all
   * would bury the eight columns everyone already uses. Each user turns on the ones
   * they care about via the toolbar's column picker and the choice persists through
   * the existing `listing_key` column-config personalization.
   */
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({
    liner_code: false,
    china_forwarder: false,
    malaysia_forwarder: false,
    consignee: false,
    loc: false,
    free_days_available: false,
    loading_date: false,
    etc_date: false,
    etd_date: false,
    eta_date: false,
    eta_delay_date: false,
    inspection_date: false,
    approval_date: false,
    gatepass_date: false,
    warehouse_arrival_date: false,
    informed_collection_date: false,
    collection_date: false,
  });
  const [packingListToDelete, setPackingListToDelete] =
    useState<PackingList | null>(null);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);

  const { data, isLoading, refetch } = usePackingLists({
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

  const columns = useMemo<ColumnDef<PackingList>[]>(() => {
    /** Clearance date column: same shape 11 times, so build it once. */
    const dateColumn = (
      key: keyof PackingList,
      title: string,
      size = 130,
    ): ColumnDef<PackingList> => ({
      accessorKey: key as string,
      header: ({ column }) => (
        <DataGridColumnHeader title={title} column={column} />
      ),
      cell: ({ row }) => {
        const value = row.original[key] as string | null | undefined;
        return value ? formatDate(new Date(value)) : '-';
      },
      size,
      meta: { headerTitle: title, skeleton: <Skeleton className="h-4 w-20" /> },
    });

    /** Clearance text column - truncated with a title, per ARCHITECTURE-RULES. */
    const textColumn = (
      key: keyof PackingList,
      title: string,
      size = 140,
    ): ColumnDef<PackingList> => ({
      accessorKey: key as string,
      header: ({ column }) => (
        <DataGridColumnHeader title={title} column={column} />
      ),
      cell: ({ row }) => {
        const value = row.original[key] as string | number | null | undefined;
        if (value === null || value === undefined || value === '') return '-';
        return (
          <span className="block truncate" title={String(value)}>
            {String(value)}
          </span>
        );
      },
      size,
      meta: { headerTitle: title, skeleton: <Skeleton className="h-4 w-24" /> },
    });

    return [
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
      // --- Container status / clearance chain. All hidden by default. ---
      textColumn('liner_code', 'Liner', 110),
      textColumn('china_forwarder', 'China Forwarder'),
      textColumn('malaysia_forwarder', 'MY Forwarder'),
      textColumn('consignee', 'Consignee', 170),
      textColumn('loc', 'Loc', 90),
      textColumn('free_days_available', 'Free Days', 110),
      dateColumn('loading_date', 'Loading'),
      dateColumn('etc_date', 'ETC', 110),
      dateColumn('etd_date', 'ETD', 110),
      dateColumn('eta_date', 'ETA', 110),
      dateColumn('eta_delay_date', 'ETA Delay'),
      dateColumn('inspection_date', 'Inspection'),
      dateColumn('approval_date', 'Approval'),
      dateColumn('gatepass_date', 'Gatepass'),
      dateColumn('warehouse_arrival_date', 'W/H Arrival'),
      dateColumn('informed_collection_date', 'Informed Collection', 170),
      dateColumn('collection_date', 'Collection'),
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
    ];
  }, []);

  const table = useReactTable({
    columns,
    data: data?.data || [],
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting, columnVisibility, rowSelection },
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    columnResizeMode: 'onChange',
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
      tableLayout={{ width: 'fixed', columnsVisibility: true, columnsResizable: true }}
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
            secondaryActions={[
              // Two or more secondary actions collapse into the toolbar's "Actions"
              // dropdown, which is where the delivery order import lives. Refresh
              // moves in with the import rather than sitting as its own icon button,
              // so this toolbar matches that page.
              {
                key: 'refresh',
                label: 'Refresh',
                icon: RefreshCw,
                onClick: () => void refetch(),
              },
              {
                key: 'import-container-status',
                label: 'Import Container Status',
                icon: Upload,
                onClick: () => setImportDialogOpen(true),
              },
            ]}
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
      <ContainerStatusImportDialog
        open={importDialogOpen}
        onOpenChange={setImportDialogOpen}
      />
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
