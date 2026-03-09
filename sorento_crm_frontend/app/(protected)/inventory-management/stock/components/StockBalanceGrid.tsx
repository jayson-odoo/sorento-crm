'use client';

import { useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Search, X, ChevronRight, Download, Upload, FileSpreadsheet, Filter, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid, DataGridApiResponse } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { useStockBalance } from '../hooks/useStock';
import { useHasPermission } from '@/hooks/usePermissions';
import { getWarehouses } from '@/app/(protected)/inventory-management/warehouses/services/warehouseService';
import type { Warehouse } from '@/app/(protected)/inventory-management/warehouses/types/warehouse.types';
import type { Stock } from '../types/stock.types';
import { TemplateDownloadDialog } from '@/components/template/TemplateDownloadDialog';
import { TemplateUploadDialog } from '@/components/template/TemplateUploadDialog';
import { exportStockBalance, bulkImportStock, validateStockImport } from '../services/stockService';
import { replaceLatestStockList, getCurrentStockListAttachment } from '@/app/(protected)/resource-management/attachments/services/attachmentService';
import { LatestImportStatusPanel } from '@/components/import-jobs/LatestImportStatusPanel';
import StockBulkDeleteDialog from './StockBulkDeleteDialog';
import { getStatusBadgeVariant } from '@/lib/status-badge';
import { useQueryClient, useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { toast } from 'sonner';
import type { ColumnOption } from '@/lib/excel-utils';
import { useRouter } from 'next/navigation';

export default function StockBalanceGrid() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'product.product_code', desc: false }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [warehouseId, setWarehouseId] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [filterOpen, setFilterOpen] = useState(false);
  const [downloadDialogOpen, setDownloadDialogOpen] = useState(false);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [exportData, setExportData] = useState<Stock[]>([]);
  const [isLoadingExport, setIsLoadingExport] = useState(false);
  const [selectedStockIds, setSelectedStockIds] = useState<Set<string>>(new Set());
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);

  const canDeleteStock = useHasPermission('inventory.stock.delete');

  const { data: stockListAttachment } = useQuery({
    queryKey: ['current-stock-list-attachment'],
    queryFn: () => getCurrentStockListAttachment(),
  });

  const { data: warehousesData } = useQuery({
    queryKey: ['warehouses-select-stock'],
    queryFn: () => getWarehouses({ pageIndex: 0, pageSize: 100, sorting: [], searchQuery: '', is_active: true }),
  });
  const warehouses: Warehouse[] = warehousesData?.data ?? [];

  const { data, isLoading } = useStockBalance({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    warehouse_id: warehouseId || undefined,
    status: statusFilter || undefined,
  });

  const pageStock = data?.data ?? [];
  const isAllSelected = pageStock.length > 0 && selectedStockIds.size === pageStock.length;
  const toggleSelection = (id: string) => {
    setSelectedStockIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const selectAll = () => {
    if (isAllSelected) {
      setSelectedStockIds(new Set());
    } else {
      setSelectedStockIds(new Set(pageStock.map((s) => s.id)));
    }
  };

  // Define column options for export
  const columnOptions: ColumnOption[] = useMemo(() => [
    { key: 'id', label: 'ID', selected: true },
    { key: 'product.product_code', label: 'Product Code', selected: true },
    { key: 'product.product_name', label: 'Product Name', selected: true },
    { key: 'product.category.category_name', label: 'Category', selected: true },
    { key: 'warehouse.warehouse_name', label: 'Warehouse', selected: true },
    { key: 'quantity', label: 'Total Quantity', selected: true },
    { key: 'reserved_quantity', label: 'Reserved Quantity', selected: true },
    { key: 'available', label: 'Available', selected: true },
    { key: 'product.reorder_level', label: 'Reorder Level', selected: false },
    { key: 'status', label: 'Status', selected: false },
  ], []);

  const handleDownloadTemplate = async () => {
    setIsLoadingExport(true);
    try {
      const allStock = await exportStockBalance();
      // Use quantity_available from backend, no need to calculate
      const stockWithAvailable = allStock.map(item => ({
        ...item,
        available: item.quantity_available ?? item.available ?? 0,
      }));
      setExportData(stockWithAvailable);
      setDownloadDialogOpen(true);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to load stock for export');
    } finally {
      setIsLoadingExport(false);
    }
  };

  const handleUploadTemplate = async (data: any[], _helpers?: unknown, file?: File) => {
    try {
      await bulkImportStock(data);
      if (file) {
        try {
          await replaceLatestStockList(file);
          queryClient.invalidateQueries({ queryKey: ['current-stock-list-attachment'] });
          queryClient.invalidateQueries({ queryKey: ['attachments'] });
        } catch (attachErr) {
          toast.error(attachErr instanceof Error ? attachErr.message : 'Failed to save as Stock List attachment');
        }
      }
      toast.success('Import job queued successfully. Processing in background. Please refresh after a while to see results.', {
        duration: 5000,
        action: {
          label: 'View Status',
          onClick: () => router.push(`/system-management/import-jobs`),
        },
      });
      queryClient.invalidateQueries({ queryKey: ['stock-balance'] });
      return;
    } catch (error) {
      throw error;
    }
  };

  const columns = useMemo<ColumnDef<Stock>[]>(
    () => [
      ...(canDeleteStock
        ? [
            {
              id: 'select',
              header: () => (
                <Checkbox
                  checked={isAllSelected}
                  onCheckedChange={selectAll}
                  aria-label="Select all"
                />
              ),
              cell: ({ row }: { row: { original: Stock } }) => (
                <Checkbox
                  checked={selectedStockIds.has(row.original.id)}
                  onCheckedChange={() => toggleSelection(row.original.id)}
                  aria-label={`Select ${row.original.product?.product_code ?? row.original.id}`}
                  onClick={(e: React.MouseEvent) => e.stopPropagation()}
                />
              ),
              size: 44,
              enableResizing: false,
            } as ColumnDef<Stock>,
          ]
        : []),
      {
        accessorKey: 'product.product_code',
        header: ({ column }) => <DataGridColumnHeader title="Product Code" column={column} />,
        cell: ({ row }) => row.original.product?.product_code || '-',
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'product.product_name',
        header: ({ column }) => <DataGridColumnHeader title="Product Name" column={column} />,
        cell: ({ row }) => row.original.product?.product_name || '-',
        size: 250,
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'product.category.category_name',
        header: ({ column }) => <DataGridColumnHeader title="Category" column={column} />,
        cell: ({ row }) => row.original.product?.category?.category_name || '-',
        size: 150,
      },
      {
        accessorKey: 'warehouse.warehouse_name',
        header: ({ column }) => <DataGridColumnHeader title="Warehouse" column={column} />,
        cell: ({ row }) => row.original.warehouse?.warehouse_name || '-',
        size: 150,
      },
      {
        accessorKey: 'available',
        header: ({ column }) => <DataGridColumnHeader title="Available" column={column} />,
        cell: ({ row }) => {
          // Use quantity_available from backend, fallback to calculated value
          const available = row.original.quantity_available ?? 
            row.original.available ?? 
            ((row.original.quantity_on_hand ?? row.original.quantity ?? 0) - (row.original.quantity_reserved ?? row.original.reserved_quantity ?? 0));
          return <span className="font-medium">{available}</span>;
        },
        size: 100,
      },
      {
        accessorKey: 'reserved_quantity',
        header: ({ column }) => <DataGridColumnHeader title="Reserved" column={column} />,
        cell: ({ row }) => row.original.quantity_reserved ?? row.original.reserved_quantity ?? 0,
        size: 100,
      },
      {
        accessorKey: 'quantity',
        header: ({ column }) => <DataGridColumnHeader title="Total" column={column} />,
        cell: ({ row }) => row.original.quantity_on_hand ?? row.original.quantity ?? 0,
        size: 100,
      },
      {
        accessorKey: 'product.reorder_level',
        header: ({ column }) => <DataGridColumnHeader title="Reorder Level" column={column} />,
        cell: ({ row }) => row.original.product?.reorder_level || '-',
        size: 120,
      },
      {
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => {
          const status = row.original.status || 'normal';
          return (
            <Badge variant={getStatusBadgeVariant(status)} appearance="ghost">
              {(status || '').charAt(0).toUpperCase() + (status || '').slice(1)}
            </Badge>
          );
        },
        size: 100,
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: () => <ChevronRight className="text-muted-foreground/70 size-3.5" />,
        size: 40,
      },
    ],
    [canDeleteStock, isAllSelected, selectedStockIds, selectAll, toggleSelection],
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

  const handleRowClick = (row: Stock) => {
    if (row.product_id && row.warehouse_id) {
      router.push(`/inventory-management/stock/${row.product_id}/${row.warehouse_id}`);
    }
  };

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      onRowClick={handleRowClick}
    >
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="relative">
              <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
              <Input
                placeholder="Search stock..."
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
            <Popover open={filterOpen} onOpenChange={setFilterOpen}>
              <PopoverTrigger asChild>
                <Button variant="outline" size="sm" className="gap-2">
                  <Filter className="size-4" />
                  Filters
                  {(warehouseId || statusFilter) && (
                    <span className="bg-primary text-primary-foreground rounded-full size-5 flex items-center justify-center text-xs">
                      {(warehouseId ? 1 : 0) + (statusFilter ? 1 : 0)}
                    </span>
                  )}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-72" align="start">
                <div className="space-y-4">
                  <div>
                    <Label>Warehouse</Label>
                    <Select value={warehouseId || 'all'} onValueChange={(v) => setWarehouseId(v === 'all' ? '' : v)}>
                      <SelectTrigger className="mt-1">
                        <SelectValue placeholder="All warehouses" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All warehouses</SelectItem>
                        {warehouses.map((w) => (
                          <SelectItem key={w.id} value={w.id}>
                            {w.warehouse_name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Status</Label>
                    <Select value={statusFilter || 'all'} onValueChange={(v) => setStatusFilter(v === 'all' ? '' : v)}>
                      <SelectTrigger className="mt-1">
                        <SelectValue placeholder="All statuses" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All statuses</SelectItem>
                        <SelectItem value="critical">Critical</SelectItem>
                        <SelectItem value="low">Low</SelectItem>
                        <SelectItem value="normal">Normal</SelectItem>
                        <SelectItem value="overstock">Overstock</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex justify-end gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setWarehouseId('');
                        setStatusFilter('');
                      }}
                    >
                      Clear
                    </Button>
                    <Button size="sm" onClick={() => setFilterOpen(false)}>
                      Apply
                    </Button>
                  </div>
                </div>
              </PopoverContent>
            </Popover>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {canDeleteStock && selectedStockIds.size > 0 && (
              <Button
                variant="outline"
                size="sm"
                className="text-destructive border-destructive/50 hover:bg-destructive/10"
                onClick={() => setBulkDeleteDialogOpen(true)}
              >
                <Trash2 className="size-4" />
                Bulk Delete ({selectedStockIds.size})
              </Button>
            )}
            {stockListAttachment ? (
              <Button variant="outline" size="sm" asChild>
                <Link href={`/resource-management/attachments/${stockListAttachment.id}`}>
                  <FileSpreadsheet className="size-4" />
                  Stock List
                </Link>
              </Button>
            ) : (
              <Button variant="outline" size="sm" disabled title="Import a stock file to create the Stock List attachment">
                <FileSpreadsheet className="size-4" />
                Stock List
              </Button>
            )}
            <Button variant="outline" onClick={handleDownloadTemplate} disabled={isLoadingExport}>
              <Download className="size-4" />
              Export
            </Button>
            <Button variant="outline" onClick={() => setUploadDialogOpen(true)}>
              <Upload className="size-4" />
              Import
            </Button>
          </div>
        </CardHeader>
        <LatestImportStatusPanel jobType="stock_import" title="Latest stock import" className="mx-5 mb-2" />
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
        filename="stock_balance_export.xlsx"
      />
      <TemplateUploadDialog
        open={uploadDialogOpen}
        onOpenChange={setUploadDialogOpen}
        onTest={async (data: any[]) => validateStockImport(data)}
        onUpload={handleUploadTemplate}
      />
      <StockBulkDeleteDialog
        open={bulkDeleteDialogOpen}
        onOpenChange={setBulkDeleteDialogOpen}
        stockIds={Array.from(selectedStockIds)}
        onSuccess={() => setSelectedStockIds(new Set())}
      />
    </DataGrid>
  );
}
