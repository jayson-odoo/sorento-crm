'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
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
  Download,
  Upload,
  AlertTriangle,
  Trash2,
  Filter,
  SlidersHorizontal,
  Columns3,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
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
import { TemplateUploadDialog } from '@/components/template/TemplateUploadDialog';
import { ListQueryFilterDialog } from '@/components/list/ListQueryFilterDialog';
import { ListQueryExportDialog } from '@/components/list/ListQueryExportDialog';
import { bulkImportOrders, importOrderTracking, validateOrderTracking, validateDeliveryOrderDetail } from '../services/orderService';
import { OrderTrackingUploadDialog } from './OrderTrackingUploadDialog';
import { OrderLinesImportDialog } from './OrderLinesImportDialog';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  buildOrderDetailSearch,
  parseOrderListNavFromSearchParams,
  type OrderListNavState,
} from '../utils/orderListNavQuery';
import type { ListQueryFilterGroup } from '@/lib/list-query/listQueryService';
import { LatestImportStatusPanel } from '@/components/import-jobs/LatestImportStatusPanel';

export default function OrdersList() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [trackingUploadOpen, setTrackingUploadOpen] = useState(false);
  const [orderLinesImportOpen, setOrderLinesImportOpen] = useState(false);
  const [filterDialogOpen, setFilterDialogOpen] = useState(false);
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const [advancedFilter, setAdvancedFilter] = useState<ListQueryFilterGroup | null>(null);
  const [selectedOrderIds, setSelectedOrderIds] = useState<Set<string>>(new Set());
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [linesFilter, setLinesFilter] = useState<'all' | 'yes' | 'no'>('all');

  const { data: orderStatuses = [] } = useOrderStatusSelectQuery();

  /** Restore list state when returning from order detail/edit (same query string as detail URLs). */
  const listNavSearchKey = useMemo(() => searchParams.toString(), [searchParams]);
  useEffect(() => {
    const nav = parseOrderListNavFromSearchParams(new URLSearchParams(listNavSearchKey));
    setPagination({ pageIndex: nav.pageIndex, pageSize: nav.pageSize });
    setSorting(nav.sorting);
    setSearchQuery(nav.searchQuery);
    setStatusFilter(nav.orderStatusId ?? 'all');
    setLinesFilter(nav.hasOrderLines);
    setAdvancedFilter(nav.advancedFilter ?? null);
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
    // Job is queued, will be processed in background
    queryClient.invalidateQueries({ queryKey: ['orders'] });
    queryClient.invalidateQueries({ queryKey: ['import-jobs'] });
    return result;
  };

  const handleRowClick = (row: Order) => {
    const orderId = row.id;
    const listNav: OrderListNavState = {
      pageIndex: pagination.pageIndex,
      pageSize: pagination.pageSize,
      orderStatusId: statusFilter === 'all' ? undefined : statusFilter,
      hasOrderLines: linesFilter,
      searchQuery,
      sorting,
      advancedFilter,
    };
    router.push(`/order-management/orders/${orderId}${buildOrderDetailSearch(listNav)}`);
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
        header: ({ column }) => <DataGridColumnHeader title="Delivery Order Number" column={column} />,
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
        header: ({ column }) => <DataGridColumnHeader title="Delivery Order Date" column={column} />,
        cell: ({ row }) => row.original.order_date ? formatDate(new Date(row.original.order_date)) : '-',
        size: 120,
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'estimated_delivery_date',
        header: ({ column }) => <DataGridColumnHeader title="Estimated Delivery" column={column} />,
        cell: ({ row }) => row.original.estimated_delivery_date ? formatDate(new Date(row.original.estimated_delivery_date)) : '-',
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

  const quickFilterActive = statusFilter !== 'all' || linesFilter !== 'all';

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
      tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
      onRefresh={() => void refetch()}
      isRefreshing={isFetching && !isLoading}
    >
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-2">
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
            <Popover>
              <PopoverTrigger asChild>
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  className="relative shrink-0"
                  title="Quick filters — status & delivery order lines"
                  aria-label="Quick filters"
                >
                  <SlidersHorizontal className="size-4" />
                  {quickFilterActive ? (
                    <span
                      className="absolute end-1 top-1 size-2 rounded-full bg-primary"
                      aria-hidden
                    />
                  ) : null}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-80" align="start">
                <div className="space-y-4">
                  <div>
                    <h4 className="text-sm font-semibold leading-none">Quick filters</h4>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="orders-quick-status" className="text-xs">
                      Status
                    </Label>
                    <Select
                      value={statusFilter}
                      onValueChange={(v) => {
                        setStatusFilter(v);
                        setPagination((p) => ({ ...p, pageIndex: 0 }));
                      }}
                    >
                      <SelectTrigger id="orders-quick-status" className="w-full">
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
                  <div className="space-y-2">
                    <Label htmlFor="orders-quick-lines" className="text-xs">
                      Delivery order lines
                    </Label>
                    <Select
                      value={linesFilter}
                      onValueChange={(v) => {
                        setLinesFilter(v as 'all' | 'yes' | 'no');
                        setPagination((p) => ({ ...p, pageIndex: 0 }));
                      }}
                    >
                      <SelectTrigger id="orders-quick-lines" className="w-full">
                        <SelectValue placeholder="Delivery order lines" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All delivery orders</SelectItem>
                        <SelectItem value="yes">With delivery order lines</SelectItem>
                        <SelectItem value="no">Without delivery order lines</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </PopoverContent>
            </Popover>
          </div>
          <div className="flex flex-wrap items-center gap-2">
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
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  title="Import"
                  aria-label="Import"
                  data-guide-target="order-management.delivery-orders.import-button"
                >
                  <Upload className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel>Import</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => setTrackingUploadOpen(true)}>
                  Import tracking
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => setOrderLinesImportOpen(true)}>
                  Import delivery order lines
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <Button variant="outline" size="sm" onClick={() => setFilterDialogOpen(true)} className="gap-1">
              <Filter className="size-4" />
              Filters
              {advancedFilter ? (
                <Badge variant="secondary" className="ms-0.5 px-1 py-0 text-[10px]">
                  On
                </Badge>
              ) : null}
            </Button>
            <Button variant="outline" size="sm" onClick={() => setExportDialogOpen(true)} className="gap-1">
              <Download className="size-4" />
              Export
            </Button>
            <DataGridColumnVisibility
              table={table}
              trigger={
                <Button variant="outline" size="sm" className="gap-1">
                  <Columns3 className="size-4" />
                  Columns
                </Button>
              }
            />
            <Button onClick={() => router.push('/order-management/orders/new')}>
              <Plus />
              Create Delivery Order
            </Button>
          </div>
        </CardHeader>
        {isError ? (
          <div className="px-5 pb-2 text-sm text-destructive">
            {error instanceof Error ? error.message : 'Failed to load delivery orders'}
          </div>
        ) : null}
        <div className="mx-5 mb-2 flex flex-wrap gap-4">
          <LatestImportStatusPanel jobType="order_tracking_import" title="Latest tracking import" />
          <LatestImportStatusPanel jobType="delivery_order_detail_import" title="Latest delivery order lines import" />
        </div>
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
      <ListQueryFilterDialog
        resourceKey="orders"
        open={filterDialogOpen}
        onOpenChange={setFilterDialogOpen}
        initialFilter={advancedFilter}
        onApply={(f) => {
          setAdvancedFilter(f);
          setPagination((p) => ({ ...p, pageIndex: 0 }));
        }}
      />
      <ListQueryExportDialog
        resourceKey="orders"
        open={exportDialogOpen}
        onOpenChange={setExportDialogOpen}
        filename="delivery_orders_export.xlsx"
        selectedRecordIds={
          selectedOrderIds.size > 0 ? Array.from(selectedOrderIds) : undefined
        }
        getPayload={() => ({
          filter: advancedFilter ?? undefined,
          quick_search: searchQuery || undefined,
          order_status_id: statusFilter === 'all' ? undefined : statusFilter,
          has_order_lines: linesFilter === 'all' ? undefined : linesFilter,
        })}
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
        onTest={validateDeliveryOrderDetail}
        onSuccess={() => {
          queryClient.invalidateQueries({ queryKey: ['orders'] });
          queryClient.invalidateQueries({ queryKey: ['import-jobs'] });
        }}
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
