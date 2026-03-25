'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import type {
  ColumnDef,
  PaginationState,
  SortingState,
} from '@tanstack/react-table';
import {
  useReactTable,
  getCoreRowModel,
  getPaginationRowModel,
} from '@tanstack/react-table';
import { Search, X, Columns3 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridColumnVisibility } from '@/components/ui/data-grid-column-visibility';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { useQuery } from '@tanstack/react-query';
import { getPickingLines, type PickingLinesListParams } from '../services/pickingLineService';
import type { PickingLineListItem } from '../types/pickingLine.types';

type SortField = 'spo_allocation' | 'product' | 'quantity_expected' | 'quantity_picked';

export default function PickingLinesList() {
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 20,
  });
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'spo_allocation', desc: false },
  ]);
  const [searchQuery, setSearchQuery] = useState('');

  const sortField = (sorting[0]?.id as SortField) || 'spo_allocation';
  const sortDir = sorting[0]?.desc ? 'desc' : 'asc';

  const params: PickingLinesListParams = useMemo(
    () => ({
      page: pagination.pageIndex + 1,
      limit: pagination.pageSize,
      sort: sortField,
      dir: sortDir,
      query: searchQuery.trim() || undefined,
    }),
    [pagination.pageIndex, pagination.pageSize, sortField, sortDir, searchQuery],
  );

  const { data, isLoading } = useQuery({
    queryKey: ['picking-lines', params],
    queryFn: () => getPickingLines(params),
  });

  const columns = useMemo<ColumnDef<PickingLineListItem>[]>(
    () => [
      {
        id: 'spo_allocation',
        accessorFn: (row) => row.spo_allocation?.spo_number ?? '',
        header: ({ column }) => (
          <DataGridColumnHeader title="SPO Allocation" column={column} />
        ),
        cell: ({ row }) => {
          const alloc = row.original.spo_allocation;
          if (!alloc) return '-';
          return (
            <Link
              href={`/procurement-management/spo-allocations/${alloc.id}`}
              className="text-primary hover:underline font-medium"
            >
              {alloc.spo_number ?? alloc.id}
            </Link>
          );
        },
        size: 160,
        meta: { skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        id: 'product',
        accessorFn: (row) => row.product?.product_code ?? '',
        header: ({ column }) => (
          <DataGridColumnHeader title="Product" column={column} />
        ),
        cell: ({ row }) => row.original.product?.product_code ?? '-',
        size: 140,
        meta: { skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'location',
        accessorFn: (row) =>
          row.source_warehouse?.warehouse_code ??
          row.destination_warehouse?.warehouse_code ??
          '',
        header: 'Location',
        cell: ({ row }) =>
          row.original.source_warehouse?.warehouse_code ??
          row.original.destination_warehouse?.warehouse_code ??
          '-',
        size: 120,
        meta: { skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'quantity_expected',
        accessorKey: 'quantity_expected',
        header: ({ column }) => (
          <DataGridColumnHeader title="Expected" column={column} />
        ),
        cell: ({ row }) => row.original.quantity_expected,
        size: 100,
        meta: { skeleton: <Skeleton className="h-4 w-12" /> },
      },
      {
        id: 'quantity_picked',
        accessorKey: 'quantity_picked',
        header: ({ column }) => (
          <DataGridColumnHeader title="Picked" column={column} />
        ),
        cell: ({ row }) => row.original.quantity_picked,
        size: 100,
        meta: { skeleton: <Skeleton className="h-4 w-12" /> },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: data?.data ?? [],
    pageCount: Math.ceil((data?.pagination?.total ?? 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    manualSorting: true,
  });

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination?.total ?? 0}
      isLoading={isLoading}
    
      tableLayout={{ columnsVisibility: true }}
    >
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
            <Input
              placeholder="Search by SPO allocation or product..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="ps-9 w-72"
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
