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
import { Plus, Search, X, ChevronRight, Download, Upload } from 'lucide-react';
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
import { useOrders } from '../hooks/useOrders';
import type { Order } from '../types/order.types';
import { formatDate } from '@/lib/helpers';
import { TemplateDownloadDialog } from '@/components/template/TemplateDownloadDialog';
import { TemplateUploadDialog } from '@/components/template/TemplateUploadDialog';
import { exportOrders, bulkImportOrders } from '../services/orderService';
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
  const [exportData, setExportData] = useState<Order[]>([]);
  const [isLoadingExport, setIsLoadingExport] = useState(false);

  const { data, isLoading } = useOrders({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
  });

  // Define column options for export
  const columnOptions: ColumnOption[] = useMemo(() => [
    { key: 'id', label: 'ID', selected: true },
    { key: 'order_number', label: 'Order Number', selected: true },
    { key: 'order_date', label: 'Order Date', selected: true },
    { key: 'customer.customer_name', label: 'Customer Name', selected: true },
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

  const handleRowClick = (row: Order) => {
    const orderId = row.id;
    router.push(`/order-management/orders/${orderId}`);
  };

  const columns = useMemo<ColumnDef<Order>[]>(
    () => [
      {
        accessorKey: 'order_number',
        header: ({ column }) => <DataGridColumnHeader title="Order Number" column={column} />,
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'order_date',
        header: ({ column }) => <DataGridColumnHeader title="Order Date" column={column} />,
        cell: ({ row }) => row.original.order_date ? formatDate(new Date(row.original.order_date)) : '-',
        size: 120,
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'customer.customer_name',
        header: ({ column }) => <DataGridColumnHeader title="Customer" column={column} />,
        cell: ({ row }) => row.original.customer?.customer_name || '-',
        size: 200,
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'order_status.status_name',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => {
          const status = row.original.order_status;
          return status ? (
            <Badge variant="secondary">{status.status_name}</Badge>
          ) : (
            '-'
          );
        },
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'promised_delivery_date',
        header: ({ column }) => <DataGridColumnHeader title="Promised Delivery" column={column} />,
        cell: ({ row }) => row.original.promised_delivery_date ? formatDate(new Date(row.original.promised_delivery_date)) : '-',
        size: 150,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'total_amount',
        header: ({ column }) => <DataGridColumnHeader title="Total Amount" column={column} />,
        cell: ({ row }) => {
          const amount = row.original.total_amount || 0;
          return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount);
        },
        size: 130,
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
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
    <DataGrid table={table} recordCount={data?.pagination.total || 0} isLoading={isLoading} onRowClick={handleRowClick}>
      <Card>
        <CardHeader className="flex-row items-center justify-between">
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
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={handleDownloadTemplate} disabled={isLoadingExport}>
              <Download className="size-4" />
              Export
            </Button>
            <Button variant="outline" onClick={() => setUploadDialogOpen(true)}>
              <Upload className="size-4" />
              Import
            </Button>
            <Button onClick={() => router.push('/order-management/orders/new')}>
              <Plus />
              Create Order
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
        filename="orders_export.xlsx"
      />
      <TemplateUploadDialog
        open={uploadDialogOpen}
        onOpenChange={setUploadDialogOpen}
        onUpload={handleUploadTemplate}
      />
    </DataGrid>
  );
}
