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
import { Handshake, Search, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
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
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { formatDateInMalaysia } from '@/lib/helpers';
import {
  useAllocationClaimMutations,
  useAllocationClaims,
} from '../../_shared/hooks/useProjectAllocations';
import type {
  AllocationClaimDirection,
  AllocationClaimRow,
  AllocationClaimState,
} from '../../_shared/types/projectAllocation.types';
import { ALLOCATION_CLAIM_STATE_LABEL } from '../../_shared/types/projectAllocation.types';
import { InfoHint } from '../../[projectId]/components/InfoHint';
import { formatQty } from '../../[projectId]/components/SalesOrderMoney';
import { ClaimRefuseDialog } from './ClaimRefuseDialog';

const STATE_BADGE: Record<AllocationClaimState, 'warning' | 'success' | 'destructive'> = {
  requested: 'warning',
  accepted: 'success',
  refused: 'destructive',
};

const DIRECTION_OPTIONS = [
  { value: 'incoming', label: 'Waiting on me' },
  { value: 'outgoing', label: 'I asked for' },
  { value: 'all', label: 'Both' },
];

const STATE_OPTIONS = [
  { value: 'all', label: 'Any answer' },
  { value: 'requested', label: ALLOCATION_CLAIM_STATE_LABEL.requested },
  { value: 'accepted', label: ALLOCATION_CLAIM_STATE_LABEL.accepted },
  { value: 'refused', label: ALLOCATION_CLAIM_STATE_LABEL.refused },
];

/**
 * The claims inbox (AC-H4).
 *
 * One project asking another for stock it is holding. Nothing moves while a claim sits in
 * "waiting", so this list is the only thing standing between a request and a phone call.
 * Refusing always opens a dialog, because a refusal without a reason sends the asker back
 * to that phone call.
 */
export function StockClaimsClient() {
  const [direction, setDirection] = React.useState<AllocationClaimDirection>('incoming');
  const [stateFilter, setStateFilter] = React.useState('requested');
  const [search, setSearch] = React.useState('');
  const [refusing, setRefusing] = React.useState<AllocationClaimRow | null>(null);
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });

  const claims = useAllocationClaims({
    direction,
    state: stateFilter === 'all' ? undefined : [stateFilter as AllocationClaimState],
    page: pagination.pageIndex + 1,
    limit: pagination.pageSize,
  });
  const { accept, refuse } = useAllocationClaimMutations();

  const all = React.useMemo(() => claims.data?.data ?? [], [claims.data]);
  const rows = React.useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return all;
    return all.filter((row) =>
      [row.product_code, row.from_project_code, row.to_project_code, row.warehouse_code]
        .filter(Boolean)
        .some((field) => (field as string).toLowerCase().includes(needle)),
    );
  }, [all, search]);

  const columns = React.useMemo<ColumnDef<AllocationClaimRow>[]>(
    () => [
      {
        id: 'from_project_code',
        header: ({ column }) => <DataGridColumnHeader title="Asked by" column={column} />,
        cell: ({ row }) => {
          const text = `${row.original.from_project_code}${
            row.original.from_project_cs_name ? `, ${row.original.from_project_cs_name}` : ''
          }`;
          return (
            <span className="block truncate font-medium" title={text}>
              {text}
            </span>
          );
        },
        size: 200,
        minSize: 140,
        meta: { headerTitle: 'Asked by', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        id: 'to_project_code',
        header: ({ column }) => <DataGridColumnHeader title="Held by" column={column} />,
        cell: ({ row }) => {
          const text = `${row.original.to_project_code}${
            row.original.to_project_cs_name ? `, ${row.original.to_project_cs_name}` : ''
          }`;
          return (
            <span className="block truncate" title={text}>
              {text}
            </span>
          );
        },
        size: 200,
        minSize: 140,
        meta: { headerTitle: 'Held by', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        id: 'product_code',
        header: ({ column }) => <DataGridColumnHeader title="Product" column={column} />,
        cell: ({ row }) => {
          const text = row.original.product_code || 'Not resolved';
          return (
            <span className="block truncate" title={row.original.product_name || text}>
              {text}
            </span>
          );
        },
        size: 170,
        minSize: 120,
        meta: { headerTitle: 'Product', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'qty',
        header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate tabular-nums" title={row.original.qty}>
            {formatQty(row.original.qty)}
          </span>
        ),
        size: 90,
        minSize: 70,
        meta: { headerTitle: 'Qty', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'warehouse_code',
        header: ({ column }) => <DataGridColumnHeader title="Location" column={column} />,
        cell: ({ row }) => {
          const text = row.original.warehouse_code || 'No location';
          return (
            <span className="block truncate" title={text}>
              {text}
            </span>
          );
        },
        size: 130,
        minSize: 100,
        meta: { headerTitle: 'Location', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'delivery_date',
        header: ({ column }) => <DataGridColumnHeader title="Needed by" column={column} />,
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
        meta: { headerTitle: 'Needed by', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'sales_order_ref',
        header: ({ column }) => <DataGridColumnHeader title="Sales order" column={column} />,
        cell: ({ row }) => {
          const text = row.original.sales_order_ref || 'Not linked';
          return (
            <span className="block truncate" title={text}>
              {text}
            </span>
          );
        },
        size: 150,
        minSize: 110,
        meta: { headerTitle: 'Sales order', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'state',
        header: ({ column }) => <DataGridColumnHeader title="Answer" column={column} />,
        cell: ({ row }) => (
          <div className="flex min-w-0 flex-col gap-0.5">
            <Badge
              variant={STATE_BADGE[row.original.state]}
              appearance="light"
              size="sm"
              className="w-fit"
            >
              {ALLOCATION_CLAIM_STATE_LABEL[row.original.state]}
            </Badge>
            {row.original.reason && (
              <span className="truncate text-xs text-muted-foreground" title={row.original.reason}>
                {row.original.reason}
              </span>
            )}
          </div>
        ),
        size: 200,
        minSize: 140,
        meta: { headerTitle: 'Answer', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'actions',
        header: '',
        enableHiding: false,
        cell: ({ row }) => {
          // Gated on the server's own answer, not on which tab is showing. The outgoing
          // view used to offer Release and Refuse on the viewer's OWN request: buttons
          // the server rejects, and with the filter on "all" the list holds both
          // directions at once, so the tab could never have decided it correctly.
          if (row.original.state === 'requested' && row.original.can_answer === false) {
            return (
              <span className="block truncate text-xs text-muted-foreground">
                Waiting on {row.original.to_project_code}
              </span>
            );
          }
          if (row.original.state !== 'requested') {
            return (
              <span className="block truncate text-xs text-muted-foreground">
                {row.original.decided_by_name
                  ? `Answered by ${row.original.decided_by_name}`
                  : 'Answered'}
              </span>
            );
          }
          return (
            <div className="flex justify-end gap-1">
              <Button
                type="button"
                size="sm"
                disabled={accept.isPending}
                onClick={() => accept.mutate(row.original.id)}
              >
                Release
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="text-destructive border-destructive/50 hover:bg-destructive/10"
                onClick={() => setRefusing(row.original)}
              >
                Refuse
              </Button>
            </div>
          );
        },
        size: 190,
        minSize: 170,
        meta: { headerTitle: 'Actions' },
      },
    ],
    [accept],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil((claims.data?.total ?? 0) / pagination.pageSize) || 0,
    getRowId: (row) => row.id,
    state: { pagination },
    onPaginationChange: setPagination,
    manualPagination: true,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
  });

  const filtersActive = (direction !== 'incoming' ? 1 : 0) + (stateFilter !== 'requested' ? 1 : 0);

  return (
    <>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2">
          <h1 className="text-xl font-semibold break-words">Stock claims</h1>
          <InfoHint label="About stock claims">
            A claim is one project asking another for stock it is holding. Nothing moves
            while a claim is waiting: the asking line keeps no stock location until it is
            released. A refusal always carries a reason.
          </InfoHint>
        </div>
      </div>

      <DataGrid
        table={table}
        recordCount={claims.data?.total ?? 0}
        isLoading={claims.isLoading}
        listingKey="projects.projects.view::project-stock-claims"
        tableLayout={{ width: 'fixed', columnsResizable: true }}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              exportConfig={false}
              searchSlot={
                <div className="relative">
                  <Search
                    className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                    aria-hidden
                  />
                  <Input
                    placeholder="Search project, product or location"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    className="w-full ps-9 sm:w-72"
                  />
                  {search.length > 0 && (
                    <Button
                      mode="icon"
                      variant="dim"
                      aria-label="Clear the search"
                      className="absolute end-1.5 top-1/2 h-6 w-6 -translate-y-1/2"
                      onClick={() => setSearch('')}
                    >
                      <X />
                    </Button>
                  )}
                </div>
              }
              filters={{
                kind: 'custom',
                active: filtersActive > 0,
                activeCount: filtersActive,
                content: (
                  <div className="space-y-3">
                    <div className="space-y-1.5">
                      <p className="text-sm font-medium">Direction</p>
                      <SearchableSelect
                        value={direction}
                        onChange={(value) => {
                          setDirection(value as AllocationClaimDirection);
                          setPagination((current) => ({ ...current, pageIndex: 0 }));
                        }}
                        options={DIRECTION_OPTIONS}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <p className="text-sm font-medium">Answer</p>
                      <SearchableSelect
                        value={stateFilter}
                        onChange={(value) => {
                          setStateFilter(value);
                          setPagination((current) => ({ ...current, pageIndex: 0 }));
                        }}
                        options={STATE_OPTIONS}
                      />
                    </div>
                  </div>
                ),
              }}
              onRefresh={async () => {
                await claims.refetch();
              }}
              isRefreshing={claims.isFetching}
            />
          </CardHeader>

          <CardTable>
            {claims.isError ? (
              <div className="px-6 py-10 text-center">
                <h3 className="text-sm font-semibold text-destructive">
                  The stock claims could not be loaded
                </h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  {claims.error instanceof Error
                    ? claims.error.message
                    : 'Try again in a moment.'}
                </p>
              </div>
            ) : !claims.isLoading && rows.length === 0 ? (
              <div className="px-6 py-10 text-center">
                <Handshake className="mx-auto size-6 text-muted-foreground" aria-hidden />
                {/* The two directions are opposite facts, so one sentence cannot be true
                    of both. Outgoing used to read "nothing is waiting on you" while
                    showing the list of things you are waiting on. */}
                <h3 className="mt-2 text-sm font-semibold">
                  {direction === 'outgoing'
                    ? 'You have not asked for anyone else\u2019s stock'
                    : direction === 'all'
                      ? 'No claims either way'
                      : 'Nothing is waiting on you'}
                </h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  {direction === 'outgoing'
                    ? 'Raise one from a sales order line under Allocation, when the stock you need is held for another project.'
                    : direction === 'all'
                      ? 'Claims appear here when a project asks another for stock it is holding. Raise one from a sales order line under Allocation.'
                      : 'Claims appear here when another project asks for stock one of yours is holding. Raise one from a sales order line under Allocation.'}
                </p>
                <Button asChild variant="outline" className="mt-4">
                  <Link href="/project-sales/pipeline">Open the pipeline</Link>
                </Button>
              </div>
            ) : (
              <ScrollArea>
                <DataGridTable />
                <ScrollBar orientation="horizontal" />
              </ScrollArea>
            )}
          </CardTable>

          {(claims.data?.total ?? 0) > pagination.pageSize && (
            <CardFooter>
              <DataGridPagination />
            </CardFooter>
          )}
        </Card>
      </DataGrid>

      {refusing && (
        <ClaimRefuseDialog
          claim={refusing}
          submitting={refuse.isPending}
          onDone={() => setRefusing(null)}
          onRefuse={(reason) => refuse.mutateAsync({ claimId: refusing.id, reason })}
        />
      )}
    </>
  );
}
