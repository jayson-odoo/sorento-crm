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
import { Plus, Search, X, ChevronRight, Download, Upload, AlertTriangle, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid, DataGridApiResponse } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import OrderBulkDeleteDialog from './OrderBulkDeleteDialog';
import { useOrders } from '../hooks/useOrders';
import { useOrderStatusSelectQuery } from '../../shared/hooks/use-order-status-select-query';
import type { Order } from '../types/order.types';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { formatDate } from '@/lib/helpers';
import { getStatusBadgeVariant } from '@/lib/status-badge';
import { TemplateDownloadDialog } from '@/components/template/TemplateDownloadDialog';
import { TemplateUploadDialog } from '@/components/template/TemplateUploadDialog';
import { exportOrders, bulkImportOrders, importOrderTracking, validateOrderTracking } from '../services/orderService';
import { OrderTrackingUploadDialog } from './OrderTrackingUploadDialog';
import { OrderLinesImportDialog } from './OrderLinesImportDialog';
import { LatestImportStatusPanel } from '@/components/import-jobs/LatestImportStatusPanel';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { ColumnOption } from '@/lib/excel-utils';

export default function OrdersList() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [downloadDialogOpen, setDownloadDialogOpen] = useState(false);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [trackingUploadOpen, setTrackingUploadOpen] = useState(false);
  const [orderLinesImportOpen, setOrderLinesImportOpen] = useState(false);
  const [exportData, setExportData] = useState<Order[]>([]);
  const [isLoadingExport, setIsLoadingExport] = useState(false);
  const [selectedOrderIds, setSelectedOrderIds] = useState<Set<string>>(new Set());
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('all');

  const { data: orderStatuses = [] } = useOrderStatusSelectQuery();

  const { data, isLoading } = useOrders({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    order_status_id: statusFilter === 'all' ? undefined : statusFilter,
  });

  // Define column options for export
  const columnOptions: ColumnOption[] = useMemo(() => [
    { key: 'id', label: 'ID', selected: true },
    { key: 'order_number', label: 'Order Number', selected: true },
    { key: 'order_date', label: 'Order Date', selected: true },
    { key: 'debtor_code', label: 'Debtor Code', selected: true },
    { key: 'debtor_name', label: 'Debtor Name', selected: true },
    { key: 'agent', label: 'Agent', selected: true },
    { key: 'is_cancelled', label: 'Cancelled', selected: true },
    { key: 'remarks_cs', label: 'Remarks CS', selected: true },
    { key: 'order_type', label: 'Order Type', selected: true },
    { key: 'order_status.status_name', label: 'Status', selected: true },
    { key: 'promised_delivery_date', label: 'Promised Delivery Date', selected: true },
    { key: 'total_amount', label: 'Total Amount', selected: true },
    { key: 'subtotal_amount', label: 'Subtotal Amount', selected: false },
    { key: 'discount_amount', label: 'Discount Amount', selected: false },
    { key: 'tax_amount', label: 'Tax Amount', selected: false },
    { key: 'remarks', label: 'Remarks', selected: false },
  ], []);

  const handleDownloadTemplate = async () => {
    setIsLoadingExport(true);
    try {
      const allOrders = await exportOrders();
      setExportData(allOrders);
      setDownloadDialogOpen(true);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to load orders for export');
    } finally {
      setIsLoadingExport(false);
    }
  };

  const handleUploadTemplate = async (data: any[]) => {
    try {
      const result = await bulkImportOrders(data);
      toast.success(`Successfully imported: ${result.created} created, ${result.updated} updated`);
      if (result.errors.length > 0) {
        toast.warning(`${result.errors.length} error(s) occurred during import`);
      }
      queryClient.invalidateQueries({ queryKey: ['orders'] });
    } catch (error) {
      throw error; // Let the dialog handle the error display
    }
  };

  const handleUploadTracking = async (file: File) => {
    const result = await importOrderTracking(file);
    // Job is queued, will be processed in background
    queryClient.invalidateQueries({ queryKey: ['orders'] });
    return result;
  };

  const handleRowClick = (row: Order) => {
    const orderId = row.id;
    const params = new URLSearchParams({
      page: String(pagination.pageIndex),
      pageSize: String(pagination.pageSize),
    });
    router.push(`/order-management/orders/${orderId}?${params.toString()}`);
  };

  const toggleOrderSelection = (orderId: string) => {
    setSelectedOrderIds((prev) => {
      const next = new Set(prev);
      if (next.has(orderId)) next.delete(orderId);
      else next.add(orderId);
      return next;
    });
  };

  const selectAllOrders = () => {
    const pageOrders = data?.data ?? [];
    if (selectedOrderIds.size === pageOrders.length) {
      setSelectedOrderIds(new Set());
    } else {
      setSelectedOrderIds(new Set(pageOrders.map((o) => o.id)));
    }
  };

  const pageOrders = data?.data ?? [];
  const isAllSelected = pageOrders.length > 0 && selectedOrderIds.size === pageOrders.length;

  const columns = useMemo<ColumnDef<Order>[]>(
    () => [
      {
        id: 'select',
        header: () => (
          <Checkbox
            checked={isAllSelected}
            onCheckedChange={selectAllOrders}
            aria-label="Select all"
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            checked={selectedOrderIds.has(row.original.id)}
            onCheckedChange={() => toggleOrderSelection(row.original.id)}
            aria-label={`Select ${row.original.order_number}`}
            onClick={(e) => e.stopPropagation()}
          />
        ),
        size: 44,
        enableResizing: false,
      },
      {
        accessorKey: 'order_number',
        header: ({ column }) => <DataGridColumnHeader title="Order Number" column={column} />,
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'debtor_name',
        header: ({ column }) => <DataGridColumnHeader title="Debtor Name" column={column} />,
        cell: ({ row }) => row.original.debtor_name || '-',
        size: 200,
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'order_date',
        header: ({ column }) => <DataGridColumnHeader title="Order Date" column={column} />,
        cell: ({ row }) => row.original.order_date ? formatDate(new Date(row.original.order_date)) : '-',
        size: 120,
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'promised_delivery_date',
        header: ({ column }) => <DataGridColumnHeader title="Promised Delivery" column={column} />,
        cell: ({ row }) => row.original.promised_delivery_date ? formatDate(new Date(row.original.promised_delivery_date)) : '-',
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'actual_delivery_date',
        header: ({ column }) => <DataGridColumnHeader title="Actual Delivery" column={column} />,
        cell: ({ row }) => row.original.actual_delivery_date ? formatDate(new Date(row.original.actual_delivery_date)) : '-',
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'delivery_days',
        header: ({ column }) => <DataGridColumnHeader title="Delivery Days (2)" column={column} />,
        cell: ({ row }) => {
          if (row.original.delivery_days === null || row.original.delivery_days === undefined) return '-';
          return (
            <div className="flex items-center gap-2">
              <span>{row.original.delivery_days}</span>
              {row.original.kpi_warning && (
                <AlertTriangle className="size-4 text-amber-500" />
              )}
            </div>
          );
        },
        size: 130,
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'debtor_code',
        header: ({ column }) => <DataGridColumnHeader title="Debtor Code" column={column} />,
        cell: ({ row }) => row.original.debtor_code || '-',
        size: 120,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'agent',
        header: ({ column }) => <DataGridColumnHeader title="Agent" column={column} />,
        cell: ({ row }) => row.original.agent || '-',
        size: 100,
        meta: { skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'is_cancelled',
        header: ({ column }) => <DataGridColumnHeader title="Cancelled" column={column} />,
        cell: ({ row }) => (row.original.is_cancelled ? 'Yes' : 'No'),
        size: 90,
        meta: { skeleton: <Skeleton className="h-4 w-12" /> },
      },
      {
        accessorKey: 'remarks_cs',
        header: ({ column }) => <DataGridColumnHeader title="Remarks CS" column={column} />,
        cell: ({ row }) => row.original.remarks_cs || '-',
        size: 220,
        minSize: 80,
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'order_type',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        cell: ({ row }) => row.original.order_type || '-',
        size: 100,
        meta: { skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'order_status.status_name',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => {
          const status = row.original.order_status;
          return status ? (
            <Badge variant={getStatusBadgeVariant(status.status_name)}>
              {status.status_name}
            </Badge>
          ) : (
            '-'
          );
        },
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: () => <ChevronRight className="text-muted-foreground/70 size-3.5" />,
        size: 40,
      },
    ],
    [selectedOrderIds, isAllSelected],
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
      tableLayout={{ width: 'fixed', columnsResizable: true }}
    >
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
              <Input
                placeholder="Search orders..."
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
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {orderStatuses.map((status) => (
                  <SelectItem key={status.id} value={status.id}>
                    {status.status_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2">
            {selectedOrderIds.size > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setBulkDeleteDialogOpen(true)}
                className="text-destructive hover:text-destructive"
              >
                <Trash2 className="size-4" />
                Bulk Delete ({selectedOrderIds.size})
              </Button>
            )}
            <Button variant="outline" onClick={() => setTrackingUploadOpen(true)}>
              <Upload className="size-4" />
              Import Tracking
            </Button>
            <Button variant="outline" onClick={() => setOrderLinesImportOpen(true)}>
              <Upload className="size-4" />
              Import order lines
            </Button>
            <Button onClick={() => router.push('/order-management/orders/new')}>
              <Plus />
              Create Order
            </Button>
          </div>
        </CardHeader>
        <LatestImportStatusPanel jobType="order_tracking_import" title="Latest order tracking import" className="mx-5 mb-2" />
        <LatestImportStatusPanel jobType="delivery_order_detail_import" title="Latest order lines import" className="mx-5 mb-2" showWhenEmpty />
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
      <TemplateDownloadDialog
        open={downloadDialogOpen}
        onOpenChange={setDownloadDialogOpen}
        data={exportData}
        columns={columnOptions}
        filename="orders_export.xlsx"
      />
      <TemplateUploadDialog
        open={uploadDialogOpen}
        onOpenChange={setUploadDialogOpen}
        onUpload={handleUploadTemplate}
      />
      <OrderTrackingUploadDialog
        open={trackingUploadOpen}
        onOpenChange={setTrackingUploadOpen}
        onTest={validateOrderTracking}
        onUpload={handleUploadTracking}
      />
      <OrderLinesImportDialog
        open={orderLinesImportOpen}
        onOpenChange={setOrderLinesImportOpen}
        onSuccess={() => queryClient.invalidateQueries({ queryKey: ['orders'] })}
      />
      <OrderBulkDeleteDialog
        open={bulkDeleteDialogOpen}
        onOpenChange={(open) => {
          setBulkDeleteDialogOpen(open);
          if (!open) setSelectedOrderIds(new Set());
        }}
        orderIds={Array.from(selectedOrderIds)}
        onSuccess={() => setSelectedOrderIds(new Set())}
      />
    </DataGrid>
  );
}
