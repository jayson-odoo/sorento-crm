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
import { Search, X, ChevronRight } from 'lucide-react';
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
import { useStockBalance } from '../hooks/useStock';
import type { Stock } from '../types/stock.types';

export default function StockBalanceGrid() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'product_code', desc: false }]);
  const [searchQuery, setSearchQuery] = useState('');

  const { data, isLoading } = useStockBalance({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
  });

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
          const available = (row.original.quantity || 0) - (row.original.reserved_quantity || 0);
          return <span className="font-medium">{available}</span>;
        },
        size: 100,
      },
      {
        accessorKey: 'reserved_quantity',
        header: ({ column }) => <DataGridColumnHeader title="Reserved" column={column} />,
        size: 100,
      },
      {
        accessorKey: 'quantity',
        header: ({ column }) => <DataGridColumnHeader title="Total" column={column} />,
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
        <CardHeader className="flex-row items-center justify-between">
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
