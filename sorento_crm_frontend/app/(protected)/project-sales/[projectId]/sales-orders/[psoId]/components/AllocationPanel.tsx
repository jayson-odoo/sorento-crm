'use client';

import * as React from 'react';
import Link from 'next/link';
import {
  ColumnDef,
  PaginationState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { ClipboardList, PackageSearch } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { formatDateInMalaysia } from '@/lib/helpers';
import { useSalesOrderAllocations } from '../../../../_shared/hooks/useProjectAllocations';
import type {
  AllocationLineRow,
  AllocationState,
} from '../../../../_shared/types/projectAllocation.types';
import { ALLOCATION_STATE_LABEL } from '../../../../_shared/types/projectAllocation.types';
import { formatQty } from '../../../components/SalesOrderMoney';
import { AllocationSourceDialog } from './AllocationSourceDialog';

const STATE_BADGE: Record<AllocationState, 'secondary' | 'success' | 'warning' | 'destructive'> = {
  unallocated: 'secondary',
  pending_claim: 'warning',
  refused: 'destructive',
  partial: 'warning',
  confirmed: 'success',
};

const STATE_OPTIONS = [
  { value: 'all', label: 'Every line' },
  { value: 'unallocated', label: ALLOCATION_STATE_LABEL.unallocated },
  { value: 'pending_claim', label: ALLOCATION_STATE_LABEL.pending_claim },
  { value: 'refused', label: ALLOCATION_STATE_LABEL.refused },
  { value: 'partial', label: ALLOCATION_STATE_LABEL.partial },
  { value: 'confirmed', label: ALLOCATION_STATE_LABEL.confirmed },
];

/**
 * Where every line on this order is coming from (AC-H1 to AC-H5). A READ.
 *
 * One row per sales order line, sourced or not: "which of the 99 still has nowhere to come
 * from" is the question this screen exists to answer, so an unsourced line is never
 * filtered away. The confirmed source is what becomes the stock location on the order
 * inquiry, which is why the column reads the line's own stock location rather than
 * recomputing it here.
 *
 * Nothing is decided here any more. Stage 1C composes and confirms a sales order's supply
 * in one transaction in Fulfilment Planning, so this panel is the evidence of that
 * decision and points at the screen that took it.
 */
export function AllocationPanel({ psoId }: { psoId: string }) {
  const allocations = useSalesOrderAllocations(psoId);

  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: search,
  } = useDebouncedSearch();
  const [stateFilter, setStateFilter] = React.useState('all');
  const [sourcing, setSourcing] = React.useState<AllocationLineRow | null>(null);
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });

  const lines = React.useMemo(() => allocations.data?.data ?? [], [allocations.data]);

  const rows = React.useMemo(() => {
    const needle = search.trim().toLowerCase();
    return lines.filter((line) => {
      if (stateFilter !== 'all' && line.state !== stateFilter) return false;
      if (!needle) return true;
      return [line.product_code, line.description, line.stock_location]
        .filter(Boolean)
        .some((field) => (field as string).toLowerCase().includes(needle));
    });
  }, [lines, search, stateFilter]);

  const columns = React.useMemo<ColumnDef<AllocationLineRow>[]>(
    () => [
      {
        id: 'line_no',
        header: ({ column }) => <DataGridColumnHeader title="#" column={column} />,
        cell: ({ row }) => <span className="tabular-nums">{row.original.line_no}</span>,
        size: 64,
        minSize: 52,
        meta: { headerTitle: '#', skeleton: <Skeleton className="h-4 w-6" /> },
      },
      {
        id: 'product_code',
        header: ({ column }) => <DataGridColumnHeader title="Product" column={column} />,
        cell: ({ row }) => {
          const code = row.original.product_code || 'Not resolved';
          return (
            <span className="block truncate font-medium" title={code}>
              {code}
            </span>
          );
        },
        size: 180,
        minSize: 120,
        meta: { headerTitle: 'Product', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'description',
        header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
        cell: ({ row }) => {
          const text = row.original.description || 'No description';
          return (
            <span className="block truncate" title={text}>
              {text}
            </span>
          );
        },
        size: 260,
        minSize: 140,
        meta: { headerTitle: 'Description', skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        id: 'qty',
        header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate tabular-nums" title={row.original.qty}>
            {`${formatQty(row.original.qty)} ${row.original.uom || ''}`.trim()}
          </span>
        ),
        size: 110,
        minSize: 80,
        meta: { headerTitle: 'Qty', skeleton: <Skeleton className="h-4 w-12" /> },
      },
      {
        id: 'delivery_date',
        header: ({ column }) => <DataGridColumnHeader title="Delivery" column={column} />,
        cell: ({ row }) =>
          row.original.delivery_date ? (
            <span className="block truncate tabular-nums">
              {formatDateInMalaysia(row.original.delivery_date)}
            </span>
          ) : (
            <span className="text-muted-foreground">No date</span>
          ),
        size: 120,
        minSize: 100,
        meta: { headerTitle: 'Delivery', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'stock_location',
        header: ({ column }) => <DataGridColumnHeader title="Stock location" column={column} />,
        cell: ({ row }) => {
          const text = row.original.stock_location || '-';
          return (
            <span
              className={`block truncate ${
                row.original.stock_location ? 'font-medium' : 'text-muted-foreground'
              }`}
              title={text}
            >
              {text}
            </span>
          );
        },
        size: 170,
        minSize: 120,
        meta: { headerTitle: 'Stock location', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'state',
        header: ({ column }) => <DataGridColumnHeader title="State" column={column} />,
        cell: ({ row }) => (
          <Badge variant={STATE_BADGE[row.original.state]} appearance="light" size="sm">
            {ALLOCATION_STATE_LABEL[row.original.state]}
          </Badge>
        ),
        size: 150,
        minSize: 120,
        meta: { headerTitle: 'State', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'held_for',
        header: ({ column }) => <DataGridColumnHeader title="Asked of" column={column} />,
        cell: ({ row }) => {
          const held = row.original.sources.find((source) => source.source_project_code);
          if (!held) return <span className="text-muted-foreground">Nobody</span>;
          const text = `${held.source_project_code}${
            held.source_project_cs_name ? `, ${held.source_project_cs_name}` : ''
          }`;
          return (
            <span className="block truncate" title={text}>
              {text}
            </span>
          );
        },
        size: 180,
        minSize: 130,
        meta: { headerTitle: 'Asked of', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'outstanding_qty',
        header: ({ column }) => <DataGridColumnHeader title="Still open" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate tabular-nums">
            {formatQty(row.original.outstanding_qty)}
          </span>
        ),
        size: 110,
        minSize: 90,
        meta: { headerTitle: 'Still open', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'actions',
        header: '',
        enableHiding: false,
        // A read, not a decision: the ranked sources behind a line are worth looking at
        // from here, and composing the supply is Fulfilment Planning's job.
        cell: ({ row }) => (
          <div className="flex justify-end">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={(event) => {
                event.stopPropagation();
                setSourcing(row.original);
              }}
            >
              View sources
            </Button>
          </div>
        ),
        size: 150,
        minSize: 130,
        meta: { headerTitle: 'Actions' },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil(rows.length / pagination.pageSize) || 0,
    getRowId: (row) => row.line_id,
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
  });

  const unsourced = lines.filter((line) => line.state === 'unallocated').length;
  const waiting = lines.filter((line) => line.state === 'pending_claim').length;

  return (
    <>
      <DataGrid
        table={table}
        recordCount={rows.length}
        isLoading={allocations.isLoading}
        listingKey="projects.projects.view::project-so-allocations"
        tableLayout={{ width: 'fixed', columnsResizable: true }}
      >
        <Card>
          <CardHeader className="block">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <p className="text-sm font-medium">Allocation</p>
                {unsourced > 0 && (
                  <Badge variant="secondary" appearance="light" size="sm">
                    {`${unsourced} without a source`}
                  </Badge>
                )}
                {waiting > 0 && (
                  <Badge variant="warning" appearance="light" size="sm">
                    {`${waiting} waiting on a claim`}
                  </Badge>
                )}
              </div>
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="text-sm text-muted-foreground">
                  Supply is composed in Fulfilment Planning.
                </span>
                <Button asChild variant="outline" size="sm">
                  <Link href="/project-sales/fulfilment-planning">
                    <ClipboardList className="size-4" aria-hidden />
                    Open Fulfilment Planning
                  </Link>
                </Button>
              </div>
            </div>
            <DataGridListToolbar
              table={table}
              exportConfig={false}
              searchSlot={
                <ListSearchInput
                  value={searchInput}
                  onChange={setSearchInput}
                  placeholder="Search product or location"
                  className="w-full sm:w-64"
                />
              }
              filters={{
                kind: 'custom',
                active: stateFilter !== 'all',
                content: (
                  <div className="space-y-2">
                    <p className="text-sm font-medium">State</p>
                    <SearchableSelect
                      value={stateFilter}
                      onChange={setStateFilter}
                      options={STATE_OPTIONS}
                    />
                  </div>
                ),
              }}
              onRefresh={async () => {
                await allocations.refetch();
              }}
              isRefreshing={allocations.isFetching}
            />
          </CardHeader>

          <CardTable>
            {allocations.isError ? (
              <div className="px-6 py-10 text-center">
                <h3 className="text-sm font-semibold text-destructive">
                  The allocation could not be loaded
                </h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  {allocations.error instanceof Error
                    ? allocations.error.message
                    : 'Try again in a moment.'}
                </p>
              </div>
            ) : !allocations.isLoading && rows.length === 0 ? (
              <div className="px-6 py-10 text-center">
                <PackageSearch className="mx-auto size-6 text-muted-foreground" aria-hidden />
                <h3 className="mt-2 text-sm font-semibold">
                  {lines.length === 0 ? 'This order has no lines' : 'No line matches'}
                </h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  {lines.length === 0
                    ? 'Rebuild the order from its purchase order and delivery schedule.'
                    : 'Clear the search or the state filter to see the rest.'}
                </p>
              </div>
            ) : (
              <DataGridTable />
            )}
          </CardTable>

          {rows.length > pagination.pageSize && (
            <CardFooter>
              <DataGridPagination />
            </CardFooter>
          )}
        </Card>
      </DataGrid>

      {sourcing && (
        <AllocationSourceDialog line={sourcing} onDone={() => setSourcing(null)} />
      )}
    </>
  );
}
