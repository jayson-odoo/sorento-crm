'use client';

import { useEffect, useMemo, useState } from 'react';
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
import { Plus, Search, X, ChevronRight } from 'lucide-react';
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
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
import { useOrderStatuses } from '../hooks/useOrderStatuses';
import type { OrderStatus } from '../types/orderStatus.types';

export default function OrderStatusesList() {
  const router = useRouter();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([{ id: 'sequence', desc: false }]);
  const [searchQuery, setSearchQuery] = useState('');
  // Final-status filter is applied client-side: the list GET has no such param
  // and order statuses are a small config set served on a single page.
  const [finalFilter, setFinalFilter] = useState<'all' | 'yes' | 'no'>('all');
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const { data, isLoading, refetch, isFetching } = useOrderStatuses({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
  });

  const rows = useMemo<OrderStatus[]>(() => {
    const all = data?.data ?? [];
    if (finalFilter === 'all') return all;
    const want = finalFilter === 'yes';
    return all.filter((r) => Boolean(r.is_final_status) === want);
  }, [data, finalFilter]);

  // Reset selection whenever the result set changes.
  useEffect(() => {
    setRowSelection({});
  }, [searchQuery, finalFilter, pagination.pageIndex, pagination.pageSize, sorting]);

  const handleRowClick = (row: OrderStatus) => {
    const orderStatusId = row.id;
    router.push(`/order-management/order-statuses/${orderStatusId}`);
  };

  const columns = useMemo<ColumnDef<OrderStatus>[]>(
    () => [
      buildSelectColumn<OrderStatus>(),
      {
        accessorKey: 'status_code',
        header: ({ column }) => <DataGridColumnHeader title="Status Code" column={column} />,
        size: 150,
        meta: { headerTitle: 'Status Code', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        accessorKey: 'status_name',
        header: ({ column }) => <DataGridColumnHeader title="Status Name" column={column} />,
        size: 200,
        meta: { headerTitle: 'Status Name', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        accessorKey: 'sequence',
        header: ({ column }) => <DataGridColumnHeader title="Sequence" column={column} />,
        size: 100,
        meta: { headerTitle: 'Sequence', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        accessorKey: 'is_final_status',
        header: ({ column }) => <DataGridColumnHeader title="Final Status" column={column} />,
        cell: ({ row }) => (
          <Badge variant={row.original.is_final_status ? 'success' : 'secondary'}>
            {row.original.is_final_status ? 'Yes' : 'No'}
          </Badge>
        ),
        size: 120,
        meta: { headerTitle: 'Final Status' },
      },
      {
        accessorKey: 'actions',
        header: '',
        cell: () => <ChevronRight className="text-muted-foreground/70 size-3.5" />,
        size: 40,
        enableHiding: false,
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
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
  });

  return (
    <DataGrid
      table={table}
      recordCount={data?.pagination.total || 0}
      isLoading={isLoading}
      onRowClick={handleRowClick}
      tableLayout={{ columnsVisibility: true }}
    >
      <Card>
        <CardHeader className="block">
          <DataGridListToolbar
            table={table}
            searchSlot={
              <div className="relative">
                <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                <Input
                  placeholder="Search delivery order statuses..."
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
            filters={{
              kind: 'custom',
              active: finalFilter !== 'all',
              activeCount: finalFilter !== 'all' ? 1 : 0,
              content: (
                <div className="space-y-4">
                  <div>
                    <Label>Final status</Label>
                    <SearchableSelect
                      value={finalFilter}
                      onChange={(v) => setFinalFilter(v as 'all' | 'yes' | 'no')}
                      options={[
                        { value: 'all', label: 'All' },
                        { value: 'yes', label: 'Final statuses' },
                        { value: 'no', label: 'Non-final statuses' },
                      ]}
                      placeholder="All"
                      triggerClassName="mt-1"
                    />
                  </div>
                  {finalFilter !== 'all' && (
                    <div className="flex justify-end">
                      <Button variant="ghost" size="sm" onClick={() => setFinalFilter('all')}>
                        Clear filters
                      </Button>
                    </div>
                  )}
                </div>
              ),
            }}
            exportConfig={{ filename: 'delivery_order_statuses_export.xlsx' }}
            onRefresh={() => void refetch()}
            isRefreshing={isFetching && !isLoading}
            primaryAction={
              <Button onClick={() => router.push('/order-management/order-statuses/new')}>
                <Plus />
                Create Delivery Order Status
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
