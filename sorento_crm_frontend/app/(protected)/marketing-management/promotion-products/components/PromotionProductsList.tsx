'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
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
import { Search, X, ChevronRight } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
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
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const { data, isLoading, refetch, isFetching } = usePromotionProductsList({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
  });

  const columns = useMemo<ColumnDef<PromotionProductListItem>[]>(
    () => [
      buildSelectColumn<PromotionProductListItem>(),
      {
        accessorKey: 'promotion.description',
        header: ({ column }) => <DataGridColumnHeader title="Promotion" column={column} />,
        size: 250,
        minSize: 150,
        maxSize: 500,
        cell: ({ row }) => {
          const label = row.original.promotion?.description || row.original.promotion_id || '-';
          return (
            <div className="truncate" title={label}>
              {label}
            </div>
          );
        },
        meta: { headerTitle: 'Promotion', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'product.product_code',
        header: ({ column }) => <DataGridColumnHeader title="Product Code" column={column} />,
        size: 150,
        cell: ({ row }) => row.original.product?.product_code || '-',
        meta: { headerTitle: 'Product Code' },
      },
      {
        accessorKey: 'product.product_name',
        header: ({ column }) => <DataGridColumnHeader title="Product Name" column={column} />,
        size: 250,
        cell: ({ row }) => row.original.product?.product_name || '-',
        meta: { headerTitle: 'Product Name' },
      },
      {
        accessorKey: 'product.list_price',
        header: ({ column }) => <DataGridColumnHeader title="List Price" column={column} />,
        size: 120,
        cell: ({ row }) => {
          const price = row.original.product?.list_price || 0;
          return new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(price);
        },
        meta: { headerTitle: 'List Price' },
      },
      {
        accessorKey: 'promotion_price',
        header: ({ column }) => <DataGridColumnHeader title="Promo Price" column={column} />,
        size: 120,
        cell: ({ row }) => {
          const price = row.original.promotion_price || row.original.product?.list_price || 0;
          return new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(price);
        },
        meta: { headerTitle: 'Promo Price' },
      },
      {
        accessorKey: 'discount_amount',
        header: ({ column }) => <DataGridColumnHeader title="Discount Amount" column={column} />,
        size: 130,
        cell: ({ row }) => {
          // Backend serializes Decimal as JSON string; coerce before numeric ops.
          const discount = Number(row.original.discount_amount ?? 0);
          return discount > 0 ? (
            <Badge variant="success">{new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(discount)}</Badge>
          ) : (
            '-'
          );
        },
        meta: { headerTitle: 'Discount Amount' },
      },
      {
        accessorKey: 'discount_percent',
        header: ({ column }) => <DataGridColumnHeader title="Discount %" column={column} />,
        size: 100,
        cell: ({ row }) => {
          const percent = Number(row.original.discount_percent ?? 0);
          return percent > 0 ? <Badge variant="info">{percent.toFixed(1)}%</Badge> : '-';
        },
        meta: { headerTitle: 'Discount %' },
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
        enableHiding: false,
      },
    ],
    [router],
  );

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
      standardToolbar={false}
      tableLayout={{
        columnsVisibility: true,
        columnsResizable: true,
      }}
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
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
            }
            exportConfig={{ filename: 'promotion_products_export.xlsx' }}
            onRefresh={() => void refetch()}
            isRefreshing={isFetching && !isLoading}
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
