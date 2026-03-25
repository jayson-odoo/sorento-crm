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
import { Search, X, ChevronRight, Columns3 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { usePromotionProductsList } from '../hooks/usePromotionProducts';
import type { PromotionProductListItem } from '../types/promotionProduct.types';

export default function PromotionProductsList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');

  const { data, isLoading } = usePromotionProductsList({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
  });

  const columns = useMemo<ColumnDef<PromotionProductListItem>[]>(
    () => [
      {
        accessorKey: 'promotion.promo_code',
        header: ({ column }) => <DataGridColumnHeader title="Promotion Code" column={column} />,
        size: 150,
        minSize: 100,
        maxSize: 500,
        cell: ({ row }) => (
          <div className="truncate" title={row.original.promotion?.promo_code || '-'}>
            {row.original.promotion?.promo_code || '-'}
          </div>
        ),
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'promotion.name',
        header: ({ column }) => <DataGridColumnHeader title="Promotion Name" column={column} />,
        size: 250,
        minSize: 150,
        maxSize: 500,
        cell: ({ row }) => (
          <div className="truncate" title={row.original.promotion?.name || '-'}>
            {row.original.promotion?.name || '-'}
          </div>
        ),
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'product.product_code',
        header: ({ column }) => <DataGridColumnHeader title="Product Code" column={column} />,
        size: 150,
        cell: ({ row }) => row.original.product?.product_code || '-',
      },
      {
        accessorKey: 'product.product_name',
        header: ({ column }) => <DataGridColumnHeader title="Product Name" column={column} />,
        size: 250,
        cell: ({ row }) => row.original.product?.product_name || '-',
      },
      {
        accessorKey: 'product.list_price',
        header: ({ column }) => <DataGridColumnHeader title="List Price" column={column} />,
        size: 120,
        cell: ({ row }) => {
          const price = row.original.product?.list_price || 0;
          return new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(price);
        },
      },
      {
        accessorKey: 'promotion_price',
        header: ({ column }) => <DataGridColumnHeader title="Promo Price" column={column} />,
        size: 120,
        cell: ({ row }) => {
          const price = row.original.promotion_price || row.original.product?.list_price || 0;
          return new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(price);
        },
      },
      {
        accessorKey: 'discount_amount',
        header: ({ column }) => <DataGridColumnHeader title="Discount Amount" column={column} />,
        size: 130,
        cell: ({ row }) => {
          const discount = row.original.discount_amount || 0;
          return discount > 0 ? (
            <Badge variant="success">{new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(discount)}</Badge>
          ) : (
            '-'
          );
        },
      },
      {
        accessorKey: 'discount_percent',
        header: ({ column }) => <DataGridColumnHeader title="Discount %" column={column} />,
        size: 100,
        cell: ({ row }) => {
          const percent = row.original.discount_percent || 0;
          return percent > 0 ? <Badge variant="info">{percent.toFixed(1)}%</Badge> : '-';
        },
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push(`/marketing-management/promotions/${row.original.promotion_id}`)}
          >
            <ChevronRight className="text-muted-foreground/70 size-3.5" />
          </Button>
        ),
        size: 40,
      },
    ],
    [router],
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
    defaultColumn: {
      minSize: 50,
      maxSize: 800,
      size: 150,
    },
  });

  return (
    <DataGrid 
      table={table} 
      recordCount={data?.pagination.total || 0} 
      isLoading={isLoading}
      tableLayout={{ columnsVisibility: true, 
        columnsResizable: true,
      }}
    >
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
            <Input
              placeholder="Search promotion products..."
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
