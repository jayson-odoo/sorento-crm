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
import { Plus, Search, X, ChevronRight } from 'lucide-react';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid, DataGridApiResponse } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { usePromotions } from '../hooks/usePromotions';
import type { Promotion } from '../types/promotion.types';
import { formatDate } from '@/lib/helpers';

export default function PromotionsList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');

  const { data, isLoading } = usePromotions({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
  });

  const columns = useMemo<ColumnDef<Promotion>[]>(
    () => [
      {
        accessorKey: 'promo_code',
        header: ({ column }) => <DataGridColumnHeader title="Promo Code" column={column} />,
        cell: ({ row }) => (
          <div className="min-w-0 max-w-full truncate" title={row.original.promo_code || ''}>
            {row.original.promo_code || '-'}
          </div>
        ),
        size: 180,
        minSize: 120,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        cell: ({ row }) => (
          <div className="min-w-0 max-w-full truncate" title={row.original.name || ''}>
            {row.original.name || '-'}
          </div>
        ),
        size: 220,
        minSize: 150,
        meta: { skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'promo_type',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        cell: ({ row }) => {
          const type = row.original.promo_type;
          const typeLabels: Record<string, string> = {
            price_override: 'Price Override',
            discount_percent: 'Discount %',
            discount_amount: 'Discount Amount',
            bundle: 'Bundle',
            other: 'Other',
          };
          return <Badge variant="secondary">{typeLabels[type as string] || type}</Badge>;
        },
        size: 150,
      },
      {
        accessorKey: 'access_levels',
        header: ({ column }) => <DataGridColumnHeader title="Access" column={column} />,
        cell: ({ row }) => {
          const levels = row.original.access_levels || [];
          if (!levels.length) return '-';
          return (
            <div className="flex flex-wrap gap-2">
              {levels.map((level) => (
                <Badge key={level} variant="secondary">
                  {level === 'dealer' ? 'Dealer' : 'End User'}
                </Badge>
              ))}
            </div>
          );
        },
        size: 160,
        minSize: 120,
      },
      {
        accessorKey: 'start_date',
        header: ({ column }) => <DataGridColumnHeader title="Start Date" column={column} />,
        cell: ({ row }) => formatDate(new Date(row.original.start_date)),
        size: 120,
      },
      {
        accessorKey: 'end_date',
        header: ({ column }) => <DataGridColumnHeader title="End Date" column={column} />,
        cell: ({ row }) => formatDate(new Date(row.original.end_date)),
        size: 120,
      },
      {
        accessorKey: 'is_active',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <Badge variant={row.original.is_active ? 'success' : 'secondary'} appearance="ghost">
            <BadgeDot />
            {row.original.is_active ? 'Active' : 'Inactive'}
          </Badge>
        ),
        size: 100,
      },
      {
        accessorKey: 'products_count',
        header: ({ column }) => <DataGridColumnHeader title="Products" column={column} />,
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

  const handleRowClick = (row: Promotion) => {
    const promotionId = row.id;
    router.push(`/marketing-management/promotions/${promotionId}`);
  };

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
              placeholder="Search promotions..."
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
          <Button onClick={() => router.push('/marketing-management/promotions/new')}>
            <Plus />
            Create Promotion
          </Button>
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
