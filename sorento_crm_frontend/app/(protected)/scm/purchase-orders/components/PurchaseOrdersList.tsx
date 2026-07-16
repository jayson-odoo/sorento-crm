'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Info, Search, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { usePurchaseOrders } from '../../hooks/usePurchaseOrders';
import { fmtDate, fmtInt } from '../../lib/format';
import type { PurchaseOrder, PurchaseOrderStatus } from '../../types/scm.types';

type BadgeDef = { variant: 'secondary' | 'primary' | 'warning' | 'success'; label: string };

/** Title-case an unknown enum value so any BE-supplied string still reads well. */
function titleCase(v: string): string {
  return v.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

const STATUS_BADGE: Partial<Record<PurchaseOrderStatus, BadgeDef>> = {
  draft: { variant: 'secondary', label: 'Draft' },
  active: { variant: 'primary', label: 'Active' },
  confirmed: { variant: 'primary', label: 'Confirmed' },
  partially_received: { variant: 'warning', label: 'Partially received' },
  received: { variant: 'success', label: 'Received' },
  cancelled: { variant: 'secondary', label: 'Cancelled' },
};

const statusBadge = (s: string): BadgeDef =>
  STATUS_BADGE[s as PurchaseOrderStatus] ?? { variant: 'secondary', label: titleCase(s) };

const STATUS_FILTER_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'active', label: 'Active' },
  { value: 'draft', label: 'Draft' },
  { value: 'confirmed', label: 'Confirmed' },
  { value: 'partially_received', label: 'Partially received' },
  { value: 'received', label: 'Received' },
  { value: 'cancelled', label: 'Cancelled' },
];

export default function PurchaseOrdersList() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  const { data, isLoading, isFetching, refetch } = usePurchaseOrders({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery,
    status: statusFilter || null,
    supplier: null,
  });

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [searchQuery, statusFilter]);

  const rows = useMemo<PurchaseOrder[]>(() => data?.data ?? [], [data]);

  const columns = useMemo<ColumnDef<PurchaseOrder>[]>(
    () => [
      {
        accessorKey: 'po_number',
        header: ({ column }) => <DataGridColumnHeader title="PO number" column={column} />,
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span className="font-medium">{row.original.po_number}</span>
            <span className="text-xs text-muted-foreground">{fmtDate(row.original.order_date)}</span>
          </div>
        ),
        size: 160,
        meta: { headerTitle: 'PO number', skeleton: <Skeleton className="h-8 w-28" /> },
      },
      {
        accessorKey: 'supplier_name',
        header: ({ column }) => <DataGridColumnHeader title="Supplier" column={column} />,
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span className="truncate" title={row.original.supplier_name}>
              {row.original.supplier_name}
            </span>
            {row.original.warehouse_name ? (
              <span className="text-xs text-muted-foreground">{row.original.warehouse_name}</span>
            ) : null}
          </div>
        ),
        size: 220,
        meta: { headerTitle: 'Supplier' },
      },
      {
        accessorKey: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => {
          const s = statusBadge(row.original.status);
          return (
            <Badge variant={s.variant} appearance="light">
              {s.label}
            </Badge>
          );
        },
        size: 170,
        meta: { headerTitle: 'Status' },
      },
      {
        accessorKey: 'expected_date',
        header: ({ column }) => <DataGridColumnHeader title="Expected date" column={column} />,
        cell: ({ row }) => (
          <span className="text-muted-foreground">{fmtDate(row.original.expected_date)}</span>
        ),
        size: 150,
        meta: { headerTitle: 'Expected date' },
      },
      {
        accessorKey: 'total_qty',
        header: ({ column }) => <DataGridColumnHeader title="Total qty" column={column} />,
        cell: ({ row }) => fmtInt(row.original.total_qty),
        size: 110,
        meta: { headerTitle: 'Total qty', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        accessorKey: 'line_count',
        header: ({ column }) => <DataGridColumnHeader title="Lines" column={column} />,
        cell: ({ row }) => fmtInt(row.original.line_count),
        size: 90,
        meta: { headerTitle: 'Lines', headerClassName: 'text-right', cellClassName: 'text-right tabular-nums' },
      },
      {
        id: 'actions',
        header: '',
        cell: () => (
          <div className="flex items-center justify-end">
            <Tooltip>
              <TooltipTrigger asChild>
                {/* Wrapper span so the tooltip fires on a disabled button. */}
                <span tabIndex={0}>
                  <Button variant="ghost" size="sm" className="h-8 gap-1 px-2 text-xs" disabled>
                    Confirm
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent>Not yet available</TooltipContent>
            </Tooltip>
          </div>
        ),
        size: 130,
        enableHiding: false,
        enableSorting: false,
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil((data?.pagination.total || 0) / pagination.pageSize),
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const filtersActive = statusFilter ? 1 : 0;

  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 p-3 text-sm text-muted-foreground">
        <Info className="mt-0.5 size-4 shrink-0" />
        <span>
          Read-only view. Creating, confirming and receiving purchase orders are not yet available.
        </span>
      </div>

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
                  <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="Search PO or supplier..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-64 ps-9"
                  />
                  {searchQuery ? (
                    <Button
                      mode="icon"
                      variant="dim"
                      className="absolute end-1.5 top-1/2 h-6 w-6 -translate-y-1/2"
                      onClick={() => setSearchQuery('')}
                      aria-label="Clear search"
                    >
                      <X />
                    </Button>
                  ) : null}
                </div>
              }
              filters={{
                kind: 'custom',
                active: filtersActive > 0,
                activeCount: filtersActive,
                content: (
                  <div className="space-y-4">
                    <div>
                      <Label className="mb-1 block">Status</Label>
                      <SearchableSelect
                        value={statusFilter}
                        onChange={setStatusFilter}
                        options={STATUS_FILTER_OPTIONS}
                        placeholder="All statuses"
                      />
                    </div>
                    {filtersActive > 0 ? (
                      <div className="flex justify-end">
                        <Button variant="ghost" size="sm" onClick={() => setStatusFilter('')}>
                          Clear filters
                        </Button>
                      </div>
                    ) : null}
                  </div>
                ),
              }}
              exportConfig={{ filename: 'purchase_orders_export.xlsx' }}
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
    </div>
  );
}
