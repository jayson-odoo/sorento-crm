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
import { formatDate } from '@/lib/helpers';
import { useQuotations } from '../hooks/useQuotations';
import type { Quotation } from '../types/quotation.types';

export default function QuotationsList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }]);
  const [searchQuery, setSearchQuery] = useState('');

  const { data, isLoading, refetch, isFetching } = useQuotations({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
  });

  const columns = useMemo<ColumnDef<Quotation>[]>(
    () => [
      {
        accessorKey: 'quote_number',
        header: ({ column }) => <DataGridColumnHeader title="Quote #" column={column} />,
        size: 200,
        cell: ({ row }) => (
          <div className="flex items-center gap-2 min-w-0">
            <span className="font-medium truncate" title={row.original.quote_number}>
              {row.original.quote_number}
            </span>
            <AutoCountSourceBadge source={row.original.source} />
          </div>
        ),
        meta: { headerTitle: 'Quote #', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        accessorKey: 'source_doc_no',
        header: ({ column }) => <DataGridColumnHeader title="Doc No" column={column} />,
        size: 160,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.source_doc_no || ''}>
            {row.original.source_doc_no || '-'}
          </span>
        ),
        meta: { headerTitle: 'Doc No' },
      },
      {
        accessorKey: 'debtor_name',
        header: ({ column }) => <DataGridColumnHeader title="Debtor" column={column} />,
        size: 240,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.debtor_name || row.original.debtor_code || ''}>
            {row.original.debtor_name || row.original.debtor_code || '-'}
          </span>
        ),
        meta: { headerTitle: 'Debtor' },
      },
      {
        accessorKey: 'doc_date',
        header: ({ column }) => <DataGridColumnHeader title="Doc Date" column={column} />,
        size: 140,
        cell: ({ row }) =>
          row.original.doc_date ? formatDate(new Date(row.original.doc_date)) : '-',
        meta: { headerTitle: 'Doc Date' },
      },
      {
        accessorKey: 'is_cancelled',
        header: ({ column }) => <DataGridColumnHeader title="Cancelled" column={column} />,
        size: 120,
        cell: ({ row }) => (
          <Badge variant={row.original.is_cancelled ? 'destructive' : 'secondary'} appearance="ghost">
            <BadgeDot />
            {row.original.is_cancelled ? 'Cancelled' : 'Active'}
          </Badge>
        ),
        meta: { headerTitle: 'Cancelled', skeleton: <Skeleton className="h-4 w-14" /> },
        enableSorting: false,
      },
      {
        accessorKey: 'sales_agent',
        header: ({ column }) => <DataGridColumnHeader title="Agent" column={column} />,
        size: 160,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.sales_agent || ''}>
            {row.original.sales_agent || '-'}
          </span>
        ),
        meta: { headerTitle: 'Agent' },
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push(`/order-management/quotations/${row.original.id}`)}
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
                  placeholder="Search quotations..."
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
            exportConfig={{ filename: 'quotations_export.xlsx' }}
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
