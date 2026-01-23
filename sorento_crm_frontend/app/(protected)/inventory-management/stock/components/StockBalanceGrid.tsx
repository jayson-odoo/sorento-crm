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
import { Search, X, ChevronRight, Download, Upload } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid, DataGridApiResponse } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useStockBalance } from '../hooks/useStock';
import type { Stock } from '../types/stock.types';
import { TemplateDownloadDialog } from '@/components/template/TemplateDownloadDialog';
import { TemplateUploadDialog } from '@/components/template/TemplateUploadDialog';
import { exportStockBalance, bulkImportStock } from '../services/stockService';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { ColumnOption } from '@/lib/excel-utils';

export default function StockBalanceGrid() {
  const queryClient = useQueryClient();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'product_code', desc: false }]);
  const [searchQuery, setSearchQuery] = useState('');
  const [quantityOperator, setQuantityOperator] = useState<string>('all');
  const [quantityValue, setQuantityValue] = useState<string>('');
  const [downloadDialogOpen, setDownloadDialogOpen] = useState(false);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [exportData, setExportData] = useState<Stock[]>([]);
  const [isLoadingExport, setIsLoadingExport] = useState(false);

  const { data, isLoading } = useStockBalance({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    quantity_operator: quantityOperator && quantityOperator !== 'all' ? quantityOperator : undefined,
    quantity_value: quantityValue || undefined,
  });

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

  const handleUploadTemplate = async (data: any[]) => {
    try {
      const result = await bulkImportStock(data);
      toast.success(`Successfully imported: ${result.created} created, ${result.updated} updated`);
      if (result.errors.length > 0) {
        toast.warning(`${result.errors.length} error(s) occurred during import`);
      }
      queryClient.invalidateQueries({ queryKey: ['stock-balance'] });
    } catch (error) {
      throw error; // Let the dialog handle the error display
    }
  };

  const columns = useMemo<ColumnDef<Stock>[]>(
    () => [
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
          const variants: Record<string, 'destructive' | 'warning' | 'success' | 'secondary'> = {
            low: 'destructive',
            critical: 'warning',
            normal: 'success',
            overstock: 'secondary',
          };
          return (
            <Badge variant={variants[status] || 'secondary'} appearance="ghost">
              {status.charAt(0).toUpperCase() + status.slice(1)}
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
    [],
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
    <DataGrid table={table} recordCount={data?.pagination.total || 0} isLoading={isLoading}>
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
            <div className="flex items-center gap-2">
              <Select
                value={quantityOperator}
                onValueChange={setQuantityOperator}
                disabled={isLoading}
              >
                <SelectTrigger className="w-32">
                  <SelectValue placeholder="Quantity" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="gt">&gt;</SelectItem>
                  <SelectItem value="gte">&gt;=</SelectItem>
                  <SelectItem value="lt">&lt;</SelectItem>
                  <SelectItem value="lte">&lt;=</SelectItem>
                  <SelectItem value="eq">=</SelectItem>
                </SelectContent>
              </Select>
              {quantityOperator && quantityOperator !== 'all' && (
                <>
                  <Input
                    type="number"
                    placeholder="Value"
                    value={quantityValue}
                    onChange={(e) => setQuantityValue(e.target.value)}
                    className="w-24"
                    disabled={isLoading}
                  />
                  {(quantityOperator !== 'all' || quantityValue) && (
                    <Button
                      mode="icon"
                      variant="dim"
                      size="sm"
                      onClick={() => {
                        setQuantityOperator('all');
                        setQuantityValue('');
                      }}
                    >
                      <X />
                    </Button>
                  )}
                </>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
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
        onUpload={handleUploadTemplate}
      />
    </DataGrid>
  );
}
