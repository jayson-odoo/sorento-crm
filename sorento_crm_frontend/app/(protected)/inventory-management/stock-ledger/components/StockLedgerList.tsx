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
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Search, Columns3 } from 'lucide-react';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { useStockLedger } from '../hooks/useStockLedger';
import type { StockLedgerEntry } from '../types/stockLedger.types';

export default function StockLedgerList() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [productId, setProductId] = useState('');
  const [warehouseId, setWarehouseId] = useState('');
  const [transactionType, setTransactionType] = useState('');

  const { data, isLoading } = useStockLedger({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    product_id: productId || undefined,
    warehouse_id: warehouseId || undefined,
    transaction_type: transactionType || undefined,
  });

  const columns = useMemo<ColumnDef<StockLedgerEntry>[]>(
    () => [
      {
        accessorKey: 'product.product_code',
        header: ({ column }) => <DataGridColumnHeader title="Product" column={column} />,
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span className="font-medium">{row.original.product?.product_code || row.original.product_id}</span>
            <span className="text-muted-foreground text-xs">{row.original.product?.product_name || '-'}</span>
          </div>
        ),
        size: 220,
        meta: { skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        accessorKey: 'warehouse.warehouse_name',
        header: ({ column }) => <DataGridColumnHeader title="Warehouse" column={column} />,
        cell: ({ row }) => row.original.warehouse?.warehouse_name || row.original.warehouse_id,
        size: 200,
        meta: { skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        accessorKey: 'transaction_type',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        size: 140,
        cell: ({ row }) => (
          <span className="text-xs font-medium text-muted-foreground">{row.original.transaction_type}</span>
        ),
      },
      {
        accessorKey: 'quantity_change',
        header: ({ column }) => <DataGridColumnHeader title="Change" column={column} />,
        cell: ({ row }) => {
          const value = row.original.quantity_change;
          const isPositive = value > 0;
          return (
            <span className={isPositive ? 'text-emerald-600 font-medium' : 'text-red-600 font-medium'}>
              {isPositive ? `+${value}` : value}
            </span>
          );
        },
        size: 120,
      },
      {
        accessorKey: 'previous_quantity',
        header: ({ column }) => <DataGridColumnHeader title="Previous" column={column} />,
        size: 120,
      },
      {
        accessorKey: 'new_quantity',
        header: ({ column }) => <DataGridColumnHeader title="New" column={column} />,
        size: 120,
      },
      {
        accessorKey: 'created_at',
        header: ({ column }) => <DataGridColumnHeader title="Created At" column={column} />,
        cell: ({ row }) => formatDateTimeInMalaysia(row.original.created_at),
        size: 200,
      },
      {
        accessorKey: 'created_by_name',
        header: ({ column }) => <DataGridColumnHeader title="Created By" column={column} />,
        cell: ({ row }) => row.original.created_by_name || row.original.created_by || '-',
        size: 180,
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
    <DataGrid table={table} recordCount={data?.pagination.total || 0} isLoading={isLoading}
      tableLayout={{ columnsVisibility: true }}
    >
      <Card>
        <CardHeader className="flex-row items-center justify-between flex-wrap gap-3">
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
            <Input
              placeholder="Filter by product ID..."
              value={productId}
              onChange={(e) => setProductId(e.target.value)}
              className="ps-9 w-64"
            />
          </div>
          <div className="relative">
            <Input
              placeholder="Warehouse ID"
              value={warehouseId}
              onChange={(e) => setWarehouseId(e.target.value)}
              className="w-52"
            />
          </div>
          <div className="relative">
            <Input
              placeholder="Transaction type"
              value={transactionType}
              onChange={(e) => setTransactionType(e.target.value)}
              className="w-52"
            />
          </div>
                    <DataGridColumnVisibility
              table={table}
              trigger={
                <Button variant="outline" size="sm" className="gap-1">
                  <Columns3 className="size-4" />
                  Columns
                </Button>
              }
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
    </DataGrid>
  );
}
