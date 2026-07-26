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
import { Search, X, ChevronRight } from 'lucide-react';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { AutoCountSourceBadge } from '@/components/common/AutoCountSourceBadge';
import { useCreditTerms } from '../hooks/useCreditTerms';
import type { CreditTerm } from '../types/creditTerm.types';

export default function CreditTermsList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');

  const { data, isLoading, refetch, isFetching } = useCreditTerms({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
  });

  const columns = useMemo<ColumnDef<CreditTerm>[]>(
    () => [
      {
        accessorKey: 'display_term',
        header: ({ column }) => <DataGridColumnHeader title="Display Term" column={column} />,
        size: 200,
        cell: ({ row }) => <span className="font-medium">{row.original.display_term}</span>,
        meta: { headerTitle: 'Display Term', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'terms',
        header: ({ column }) => <DataGridColumnHeader title="Terms" column={column} />,
        size: 260,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.terms || ''}>
            {row.original.terms || '-'}
          </span>
        ),
        meta: { headerTitle: 'Terms' },
      },
      {
        accessorKey: 'term_days',
        header: ({ column }) => <DataGridColumnHeader title="Term Days" column={column} />,
        size: 120,
        cell: ({ row }) => (row.original.term_days ?? '-'),
        meta: { headerTitle: 'Term Days' },
      },
      {
        accessorKey: 'is_active',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        size: 110,
        cell: ({ row }) => (
          <Badge variant={row.original.is_active ? 'success' : 'secondary'} appearance="ghost">
            <BadgeDot />
            {row.original.is_active ? 'Active' : 'Inactive'}
          </Badge>
        ),
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-4 w-14" /> },
      },
      {
        accessorKey: 'source',
        header: ({ column }) => <DataGridColumnHeader title="Source" column={column} />,
        size: 130,
        cell: ({ row }) => <AutoCountSourceBadge source={row.original.source} />,
        meta: { headerTitle: 'Source' },
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="sm"
            onClick={() =>
              router.push(`/master-data-management/credit-terms/${row.original.id}`)
            }
          >
            <ChevronRight className="text-muted-foreground/70 size-3.5" />
          </Button>
        ),
        size: 60,
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
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <div className="relative">
                <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                <Input
                  placeholder="Search credit terms..."
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
            exportConfig={{ filename: 'credit_terms_export.xlsx' }}
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
