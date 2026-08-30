'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { FileClock, LayoutGrid } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { usePlanningChangeBatches } from '../../_shared/hooks/usePlanningChanges';
import {
  PLANNING_CHANGE_SOURCE_KIND_LABEL,
  type PlanningChangeBatchSummary,
} from '../../_shared/types/planningChange.types';
import { PageHeader } from '@/components/common/PageHeader';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';

/**
 * Where a batch is decided: the fulfilment board, opened on the orders it moved (AC-P3-1).
 *
 * There is no batch page any more. A planning change is a change to a PLAN, and the plan has
 * one screen; reviewing it somewhere else meant two vocabularies for one decision (the rule
 * table's `keep` / `release` / `retire` on one screen, `Buy` / `Use own location` on the
 * other) and two places to press Confirm.
 */
export function planningChangeBoardHref(batch: {
  id: string;
  so_numbers?: string[] | null;
}): string {
  const orders = (batch.so_numbers ?? []).join(',');
  const search = new URLSearchParams();
  if (orders) search.set('orders', orders);
  search.set('batch', batch.id);
  return `/project-sales/fulfilment-planning?${search.toString()}`;
}

const STATE_TABS: { value: 'all' | 'pending' | 'applied'; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'pending', label: 'Pending' },
  { value: 'applied', label: 'Applied' },
];

/**
 * Every batch a re-uploaded AutoCount book raised (AC-R10), newest upload first.
 *
 * A record, never deleted: the batch reads exactly as it did at review plus what was applied,
 * so a planner who missed the upload-screen card can still find and act on it here.
 */
export function PlanningChangesListClient() {
  const router = useRouter();
  const {
    value: search,
    setValue: setSearch,
    debouncedValue: debounced,
    isSettling: debouncedSettling,
  } = useDebouncedSearch();
  const [stateFilter, setStateFilter] = React.useState<'all' | 'pending' | 'applied'>('all');
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });

  React.useEffect(() => {
    setPagination((previous) => ({ ...previous, pageIndex: 0 }));
  }, [debounced, stateFilter]);

  const params = React.useMemo(
    () => ({
      query: debounced || undefined,
      state: stateFilter === 'all' ? undefined : stateFilter,
      page: pagination.pageIndex + 1,
      limit: pagination.pageSize,
    }),
    [debounced, stateFilter, pagination],
  );

  const list = usePlanningChangeBatches(params);
  const rows = React.useMemo(() => list.data?.data ?? [], [list.data]);
  const total = list.data?.total ?? 0;
  const filtered = Boolean(debounced || stateFilter !== 'all');

  const columns = React.useMemo<ColumnDef<PlanningChangeBatchSummary>[]>(
    () => [
      {
        accessorKey: 'created_at',
        header: ({ column }) => <DataGridColumnHeader title="Uploaded" column={column} />,
        size: 150,
        meta: { headerTitle: 'Uploaded' },
        cell: ({ row }) => (
          <span className="whitespace-nowrap tabular-nums">
            {formatDateTimeInMalaysia(row.original.created_at)}
          </span>
        ),
      },
      {
        accessorKey: 'created_by_name',
        header: ({ column }) => <DataGridColumnHeader title="Uploaded by" column={column} />,
        size: 140,
        meta: { headerTitle: 'Uploaded by' },
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.created_by_name ?? undefined}>
            {row.original.created_by_name ?? '-'}
          </span>
        ),
      },
      {
        accessorKey: 'source',
        header: ({ column }) => <DataGridColumnHeader title="Source file" column={column} />,
        size: 220,
        meta: { headerTitle: 'Source file' },
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.source.file_name}>
            {row.original.source.file_name}
          </span>
        ),
      },
      {
        id: 'source_kind',
        header: ({ column }) => <DataGridColumnHeader title="Source" column={column} />,
        size: 130,
        meta: { headerTitle: 'Source' },
        cell: ({ row }) => (
          <span className="block truncate">
            {PLANNING_CHANGE_SOURCE_KIND_LABEL[row.original.source.kind]}
          </span>
        ),
      },
      {
        accessorKey: 'order_count',
        header: ({ column }) => <DataGridColumnHeader title="Orders" column={column} />,
        size: 90,
        meta: { headerTitle: 'Orders' },
        cell: ({ row }) => <span className="tabular-nums">{row.original.order_count}</span>,
      },
      {
        accessorKey: 'line_count',
        header: ({ column }) => <DataGridColumnHeader title="Lines" column={column} />,
        size: 90,
        meta: { headerTitle: 'Lines' },
        cell: ({ row }) => <span className="tabular-nums">{row.original.line_count}</span>,
      },
      {
        accessorKey: 'pending_count',
        header: ({ column }) => <DataGridColumnHeader title="Pending" column={column} />,
        size: 100,
        meta: { headerTitle: 'Pending' },
        cell: ({ row }) => <span className="tabular-nums">{row.original.pending_count}</span>,
      },
      {
        id: 'applied',
        header: ({ column }) => <DataGridColumnHeader title="Applied" column={column} />,
        size: 200,
        meta: { headerTitle: 'Applied' },
        cell: ({ row }) =>
          row.original.applied_at ? (
            <span className="block truncate">
              {`${formatDateTimeInMalaysia(row.original.applied_at)}${
                row.original.applied_by_name ? ` by ${row.original.applied_by_name}` : ''
              }`}
            </span>
          ) : (
            <span className="text-muted-foreground">Not applied</span>
          ),
      },
      {
        id: 'state',
        header: ({ column }) => <DataGridColumnHeader title="State" column={column} />,
        size: 130,
        meta: { headerTitle: 'State' },
        cell: ({ row }) => <BatchStatePill batch={row.original} />,
      },
      {
        id: 'actions',
        header: '',
        size: 90,
        enableSorting: false,
        enableHiding: false,
        cell: ({ row }) => (
          <div className="flex justify-end">
            <Button asChild variant="outline" size="sm" onClick={(e) => e.stopPropagation()}>
              <Link href={planningChangeBoardHref(row.original)}>
                <LayoutGrid className="size-4" aria-hidden />
                Plan
              </Link>
            </Button>
          </div>
        ),
      },
    ],
    [],
  );

  const table = useReactTable({
    data: rows,
    columns,
    getRowId: (row) => row.id,
    state: { pagination },
    onPaginationChange: setPagination,
    pageCount: Math.max(1, Math.ceil(total / pagination.pageSize)),
    manualPagination: true,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
  });

  return (
    <div className="space-y-5">
      <PageHeader
        title="Planning changes"
      >
        <p className="mt-0.5 text-sm text-muted-foreground">
          Every re-uploaded sales order book that moved a planned line.
        </p>
      </PageHeader>

      <nav
        aria-label="State"
        className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/30 p-2"
      >
        {STATE_TABS.map((tab) => (
          <Button
            key={tab.value}
            type="button"
            size="sm"
            variant={stateFilter === tab.value ? 'primary' : 'ghost'}
            onClick={() => setStateFilter(tab.value)}
          >
            {tab.label}
          </Button>
        ))}
      </nav>

      <DataGrid
        table={table}
        recordCount={total}
        isLoading={list.isLoading}
        listingKey="projects.projects.view::project-planning-changes"
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        onRowClick={(row) => router.push(planningChangeBoardHref(row))}
        emptyMessage={
          <div className="px-6 py-10 text-center">
            <FileClock className="mx-auto size-6 text-muted-foreground" aria-hidden />
            <h3 className="mt-2 text-sm font-semibold">
              {filtered ? 'No batches match' : 'No planning changes yet'}
            </h3>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
              {filtered
                ? 'Clear the filters to see every planning change.'
                : 'A re-uploaded sales order book that moves a planned line will appear here.'}
            </p>
          </div>
        }
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              exportConfig={false}
              searchSlot={
                <ListSearchInput
                  value={search}
                  onChange={setSearch}
                  isSettling={debouncedSettling}
                  placeholder="Search by uploader or file"
                  aria-label="Search planning change batches"
                  className="w-full"
                />
              }
              onRefresh={async () => {
                await list.refetch();
              }}
              isRefreshing={list.isFetching && !list.isLoading}
            />
          </CardHeader>

          <CardTable>
            {list.isError ? (
              <div className="px-6 py-10 text-center">
                <h3 className="text-sm font-semibold text-destructive">
                  Planning changes could not be loaded
                </h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  {list.error instanceof Error ? list.error.message : 'Try again in a moment.'}
                </p>
              </div>
            ) : (
              <DataGridTable />
            )}
          </CardTable>

          {total > pagination.pageSize && (
            <CardFooter>
              <DataGridPagination />
            </CardFooter>
          )}
        </Card>
      </DataGrid>
    </div>
  );
}

function BatchStatePill({ batch }: { batch: PlanningChangeBatchSummary }) {
  if (!batch.applied_at) {
    return (
      <Badge variant="warning" appearance="light">
        Pending
      </Badge>
    );
  }
  if (batch.failed_count > 0) {
    return (
      <Badge variant="destructive" appearance="light">
        Partly failed
      </Badge>
    );
  }
  return (
    <Badge variant="success" appearance="light">
      Applied
    </Badge>
  );
}

export default PlanningChangesListClient;
