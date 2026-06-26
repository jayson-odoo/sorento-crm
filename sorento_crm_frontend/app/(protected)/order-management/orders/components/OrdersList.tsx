'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
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
import {
  Plus,
  Search,
  X,
  ChevronRight,
  Upload,
  AlertTriangle,
  Trash2,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
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
import { TemplateUploadDialog } from '@/components/template/TemplateUploadDialog';
import { bulkImportOrders, importOrderTracking, validateOrderTracking, validateDeliveryOrderDetail } from '../services/orderService';
import { OrderTrackingUploadDialog } from './OrderTrackingUploadDialog';
import { OrderLinesImportDialog } from './OrderLinesImportDialog';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { buildDetailSearch, parseDetailSearch } from '@/lib/listNavQuery';
import type { ListQueryFilterGroup } from '@/lib/list-query/listQueryService';
import { useImportJobDrawer } from '@/components/upload-activity';

/** Encode the advanced (POST list-query) filter for the detail URL round-trip. */
function encodeAdvancedFilter(filter: ListQueryFilterGroup | null): string | undefined {
  if (filter == null) return undefined;
  try {
    return encodeURIComponent(JSON.stringify(filter));
  } catch {
    return undefined;
  }
}

/** Decode the advanced filter carried back from a detail URL (invalid -> null). */
function decodeAdvancedFilter(raw: string | undefined): ListQueryFilterGroup | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(decodeURIComponent(raw)) as ListQueryFilterGroup;
    if (
      parsed &&
      typeof parsed === 'object' &&
      (parsed.op === 'and' || parsed.op === 'or') &&
      Array.isArray(parsed.children)
    ) {
      return parsed;
    }
  } catch {
    /* ignore malformed / oversized */
  }
  return null;
}

export default function OrdersList() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { notifyImportQueued } = useImportJobDrawer();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [trackingUploadOpen, setTrackingUploadOpen] = useState(false);
  const [orderLinesImportOpen, setOrderLinesImportOpen] = useState(false);
  const [advancedFilter, setAdvancedFilter] = useState<ListQueryFilterGroup | null>(null);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [linesFilter, setLinesFilter] = useState<'all' | 'yes' | 'no'>('all');

  const { data: orderStatuses = [] } = useOrderStatusSelectQuery();

  /** Restore list state when returning from order detail/edit (same query string as detail URLs). */
  const listNavSearchKey = useMemo(() => searchParams.toString(), [searchParams]);
  useEffect(() => {
    const parsed = parseDetailSearch(new URLSearchParams(listNavSearchKey));
    setPagination({ pageIndex: parsed.pageIndex, pageSize: parsed.pageSize });
    setSorting(parsed.sorting);
    setSearchQuery(parsed.searchQuery);
    setStatusFilter(parsed.filters.order_status_id ?? 'all');
    const hol = parsed.filters.has_order_lines;
    setLinesFilter(hol === 'yes' || hol === 'no' ? hol : 'all');
    setAdvancedFilter(decodeAdvancedFilter(parsed.filters.advFilter));
  }, [listNavSearchKey]);

  const { data, isLoading, isError, error, refetch, isFetching } = useOrders({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    order_status_id: statusFilter === 'all' ? undefined : statusFilter,
    has_order_lines: linesFilter,
    advancedFilter: advancedFilter ?? undefined,
  });

  const handleUploadTemplate = async (data: unknown[]) => {
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
    // Job is queued, will be processed in background — progress in the upload drawer
    notifyImportQueued();
    queryClient.invalidateQueries({ queryKey: ['orders'] });
    queryClient.invalidateQueries({ queryKey: ['import-jobs'] });
    return result;
  };

  const handleRowClick = (row: Order) => {
    const orderId = row.id;
    // Carry the active list query into the detail URL so its prev/next pager
    // walks the same filtered+sorted set (same param names as the list GET).
    const search = buildDetailSearch(
      {
        pageIndex: pagination.pageIndex,
        pageSize: pagination.pageSize,
        sorting,
        searchQuery,
      },
      {
        order_status_id: statusFilter === 'all' ? undefined : statusFilter,
        has_order_lines: linesFilter !== 'all' ? linesFilter : undefined,
        // advFilter is restored on return but ignored by the GET neighbours
        // endpoint (which mirrors the list GET, not the POST list-query).
        advFilter: encodeAdvancedFilter(advancedFilter),
      },
    );
    const qs = search ? `?${search}` : '';
    router.push(`/order-management/orders/${orderId}${qs}`);
  };

  const columns = useMemo<ColumnDef<Order>[]>(
    () => [
      buildSelectColumn<Order>(),
      {
        accessorKey: 'order_number',
        header: ({ column }) => <DataGridColumnHeader title="Delivery Order Number" column={column} />,
        size: 150,
        meta: { headerTitle: 'Delivery Order Number', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'debtor_name',
        header: ({ column }) => <DataGridColumnHeader title="Debtor Name" column={column} />,
        cell: ({ row }) => row.original.debtor_name || '-',
        size: 200,
        meta: { headerTitle: 'Debtor Name', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'order_date',
        header: ({ column }) => <DataGridColumnHeader title="Delivery Order Date" column={column} />,
        cell: ({ row }) => row.original.order_date ? formatDate(new Date(row.original.order_date)) : '-',
        size: 120,
        meta: { headerTitle: 'Delivery Order Date', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'estimated_delivery_date',
        header: ({ column }) => <DataGridColumnHeader title="Estimated Delivery" column={column} />,
        cell: ({ row }) => row.original.estimated_delivery_date ? formatDate(new Date(row.original.estimated_delivery_date)) : '-',
        size: 150,
        meta: { headerTitle: 'Estimated Delivery', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'actual_delivery_date',
        header: ({ column }) => <DataGridColumnHeader title="Actual Delivery" column={column} />,
        cell: ({ row }) => row.original.actual_delivery_date ? formatDate(new Date(row.original.actual_delivery_date)) : '-',
        size: 150,
        meta: { headerTitle: 'Actual Delivery', skeleton: <Skeleton className="h-4 w-24" /> },
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
        meta: { headerTitle: 'Delivery Days (2)', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'debtor_code',
        header: ({ column }) => <DataGridColumnHeader title="Debtor Code" column={column} />,
        cell: ({ row }) => row.original.debtor_code || '-',
        size: 120,
        meta: { headerTitle: 'Debtor Code', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'agent',
        header: ({ column }) => <DataGridColumnHeader title="Agent" column={column} />,
        cell: ({ row }) => row.original.agent || '-',
        size: 100,
        meta: { headerTitle: 'Agent', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'is_cancelled',
        header: ({ column }) => <DataGridColumnHeader title="Cancelled" column={column} />,
        cell: ({ row }) => (row.original.is_cancelled ? 'Yes' : 'No'),
        size: 90,
        meta: { headerTitle: 'Cancelled', skeleton: <Skeleton className="h-4 w-12" /> },
      },
      {
        accessorKey: 'remarks_cs',
        header: ({ column }) => <DataGridColumnHeader title="Remarks CS" column={column} />,
        cell: ({ row }) => row.original.remarks_cs || '-',
        size: 220,
        minSize: 80,
        meta: { headerTitle: 'Remarks CS', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'order_type',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        cell: ({ row }) => row.original.order_type || '-',
        size: 100,
        meta: { headerTitle: 'Type', skeleton: <Skeleton className="h-4 w-16" /> },
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
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-4 w-24" /> },
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

  const quickFilterActive = statusFilter !== 'all' || linesFilter !== 'all';

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
      tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <div className="relative">
                <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                <Input
                  placeholder="Search delivery orders..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="ps-9 w-64 max-w-full"
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
              resourceKey: 'orders',
              advancedFilter,
              onApply: (f) => {
                setAdvancedFilter(f);
                setPagination((p) => ({ ...p, pageIndex: 0 }));
              },
              getPayload: () => ({
                filter: advancedFilter ?? undefined,
                quick_search: searchQuery || undefined,
                order_status_id: statusFilter === 'all' ? undefined : statusFilter,
                has_order_lines: linesFilter === 'all' ? undefined : linesFilter,
              }),
            }}
            exportConfig={{
              kind: 'listQuery',
              resourceKey: 'orders',
              filename: 'delivery_orders_export.xlsx',
              getPayload: () => ({
                filter: advancedFilter ?? undefined,
                quick_search: searchQuery || undefined,
                order_status_id: statusFilter === 'all' ? undefined : statusFilter,
                has_order_lines: linesFilter === 'all' ? undefined : linesFilter,
              }),
            }}
            onRefresh={() => void refetch()}
            isRefreshing={isFetching && !isLoading}
            primaryAction={
              <Button onClick={() => router.push('/order-management/orders/new')}>
                <Plus />
                Create Delivery Order
              </Button>
            }
            secondaryActions={[
              {
                key: 'import-tracking',
                label: 'Import tracking',
                icon: Upload,
                onClick: () => setTrackingUploadOpen(true),
                dataGuideTarget: 'order-management.delivery-orders.import-button',
              },
              {
                key: 'import-lines',
                label: 'Import delivery order lines',
                icon: Upload,
                onClick: () => setOrderLinesImportOpen(true),
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
          {/* Quick status / lines filters retained below the canonical toolbar
              (these are server-side params, distinct from the advanced filter). */}
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <Label htmlFor="orders-quick-status" className="text-xs text-muted-foreground">
                Status
              </Label>
              <Select
                value={statusFilter}
                onValueChange={(v) => {
                  setStatusFilter(v);
                  setPagination((p) => ({ ...p, pageIndex: 0 }));
                }}
              >
                <SelectTrigger id="orders-quick-status" className="h-8 w-48">
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
              <Label htmlFor="orders-quick-lines" className="text-xs text-muted-foreground">
                Delivery order lines
              </Label>
              <Select
                value={linesFilter}
                onValueChange={(v) => {
                  setLinesFilter(v as 'all' | 'yes' | 'no');
                  setPagination((p) => ({ ...p, pageIndex: 0 }));
                }}
              >
                <SelectTrigger id="orders-quick-lines" className="h-8 w-56">
                  <SelectValue placeholder="Delivery order lines" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All delivery orders</SelectItem>
                  <SelectItem value="yes">With delivery order lines</SelectItem>
                  <SelectItem value="no">Without delivery order lines</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {quickFilterActive && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setStatusFilter('all');
                  setLinesFilter('all');
                  setPagination((p) => ({ ...p, pageIndex: 0 }));
                }}
              >
                Clear quick filters
              </Button>
            )}
          </div>
        </CardHeader>
        {isError ? (
          <div className="px-5 pb-2 text-sm text-destructive">
            {error instanceof Error ? error.message : 'Failed to load delivery orders'}
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
        onTest={validateDeliveryOrderDetail}
        onSuccess={() => {
          notifyImportQueued();
          queryClient.invalidateQueries({ queryKey: ['orders'] });
          queryClient.invalidateQueries({ queryKey: ['import-jobs'] });
        }}
      />
      <OrderBulkDeleteDialog
        open={bulkDeleteDialogOpen}
        onOpenChange={setBulkDeleteDialogOpen}
        orderIds={selectedRowIds(table)}
        onSuccess={() => setRowSelection({})}
      />
    </DataGrid>
  );
}
