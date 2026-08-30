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
import { CheckCircle2, Search, X } from 'lucide-react';
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
import { useDivergences } from '../../_shared/hooks/useSoDivergence';
import type { DivergenceSummary } from '../../_shared/types/soDivergence.types';
import { InfoHint } from '../../[projectId]/components/InfoHint';
import { PageHeader } from '@/components/common/PageHeader';

const STATUS_OPTIONS = [
  { value: 'open', label: 'Still to reconcile' },
  { value: 'resolved', label: 'Reconciled' },
  { value: 'all', label: 'Any' },
];

/**
 * How old an unanswered reconciliation is allowed to look calm.
 *
 * A difference against AutoCount is not urgent on the day it lands - somebody has to read
 * two documents - but a week of them is the stack AC-N6 exists to surface. The bands are
 * the escalation the client already reads elsewhere in the module.
 */
function ageTone(days: number): 'secondary' | 'warning' | 'destructive' {
  if (days >= 7) return 'destructive';
  if (days >= 3) return 'warning';
  return 'secondary';
}

/**
 * The management list (AC-N6).
 *
 * Every row is a sales order whose amendments are BLOCKED until somebody answers it, so
 * the age column is the point of the screen rather than decoration: a reconciliation
 * nobody opens is a sales order nobody can revise.
 */
export function DivergenceListClient() {
  const [statusFilter, setStatusFilter] = React.useState('open');
  const [search, setSearch] = React.useState('');
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });

  const divergences = useDivergences({
    status: statusFilter === 'all' ? undefined : statusFilter,
    page: pagination.pageIndex + 1,
    limit: pagination.pageSize,
  });

  const all = React.useMemo(() => divergences.data?.data ?? [], [divergences.data]);
  const rows = React.useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return all;
    return all.filter((row) =>
      [row.project_title, row.provisional_ref, row.autocount_doc_no, row.sales_order_ref]
        .filter(Boolean)
        .some((field) => (field as string).toLowerCase().includes(needle)),
    );
  }, [all, search]);

  const columns = React.useMemo<ColumnDef<DivergenceSummary>[]>(
    () => [
      {
        id: 'project_title',
        header: ({ column }) => <DataGridColumnHeader title="Project" column={column} />,
        cell: ({ row }) => {
          const text = row.original.project_title || 'Unnamed project';
          return (
            <span className="block truncate font-medium" title={text}>
              {text}
            </span>
          );
        },
        size: 220,
        minSize: 150,
        meta: { headerTitle: 'Project', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        id: 'sales_order_ref',
        header: ({ column }) => <DataGridColumnHeader title="Sales order" column={column} />,
        cell: ({ row }) => {
          // The AutoCount number once adopted, else our own reference. Never the id.
          const text = row.original.sales_order_ref || row.original.provisional_ref || '';
          return (
            <span className="block truncate tabular-nums" title={text}>
              {text}
            </span>
          );
        },
        size: 160,
        minSize: 120,
        meta: { headerTitle: 'Sales order', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'differing_count',
        header: ({ column }) => <DataGridColumnHeader title="Differences" column={column} />,
        cell: ({ row }) => (
          <div className="flex min-w-0 flex-col gap-0.5">
            <span className="truncate tabular-nums">
              {row.original.differing_count} of {row.original.compared_count}
            </span>
            {row.original.unresolved_count > 0 && (
              <span className="truncate text-xs text-muted-foreground">
                {row.original.unresolved_count} unanswered
              </span>
            )}
          </div>
        ),
        size: 130,
        minSize: 110,
        meta: { headerTitle: 'Differences', skeleton: <Skeleton className="h-4 w-14" /> },
      },
      {
        id: 'detected_at',
        header: ({ column }) => <DataGridColumnHeader title="Found" column={column} />,
        cell: ({ row }) =>
          row.original.detected_at ? (
            <span className="block truncate tabular-nums">
              {formatDateInMalaysia(row.original.detected_at)}
            </span>
          ) : (
            <span className="text-muted-foreground">Unknown</span>
          ),
        size: 120,
        minSize: 100,
        meta: { headerTitle: 'Found', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'age_days',
        header: ({ column }) => <DataGridColumnHeader title="Waiting" column={column} />,
        cell: ({ row }) => {
          if (row.original.status === 'resolved') {
            return <span className="text-muted-foreground">Answered</span>;
          }
          const days = row.original.age_days;
          return (
            <Badge variant={ageTone(days)} appearance="light" size="sm" className="w-fit">
              {days === 0 ? 'Today' : `${days} day${days === 1 ? '' : 's'}`}
            </Badge>
          );
        },
        size: 110,
        minSize: 90,
        meta: { headerTitle: 'Waiting', skeleton: <Skeleton className="h-4 w-14" /> },
      },
      {
        id: 'status',
        header: ({ column }) => <DataGridColumnHeader title="State" column={column} />,
        cell: ({ row }) => (
          <div className="flex min-w-0 flex-col gap-0.5">
            <Badge
              variant={row.original.status === 'resolved' ? 'success' : 'warning'}
              appearance="light"
              size="sm"
              className="w-fit"
            >
              {row.original.status === 'resolved' ? 'Reconciled' : 'Amendments blocked'}
            </Badge>
            {row.original.corrective_publish_required && (
              <span className="truncate text-xs text-muted-foreground">
                Corrective file to send
              </span>
            )}
          </div>
        ),
        size: 180,
        minSize: 140,
        meta: { headerTitle: 'State', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'actions',
        header: '',
        enableHiding: false,
        cell: ({ row }) => (
          <div className="flex justify-end">
            <Button asChild size="sm" variant="outline">
              <Link
                href={`/project-sales/${row.original.project_id}/sales-orders/${row.original.project_sales_order_id}/divergence`}
              >
                {row.original.status === 'resolved' ? 'View' : 'Reconcile'}
              </Link>
            </Button>
          </div>
        ),
        size: 120,
        minSize: 110,
        meta: { headerTitle: 'Actions' },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil((divergences.data?.total ?? 0) / pagination.pageSize) || 0,
    getRowId: (row) => row.id,
    state: { pagination },
    onPaginationChange: setPagination,
    manualPagination: true,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
  });

  const filtersActive = statusFilter !== 'open' ? 1 : 0;

  return (
    <>
      <PageHeader
        title={
          <span className="inline-flex flex-wrap items-center gap-2">
            AutoCount differences
            <InfoHint label="About AutoCount differences">
              While a sales order lives in both systems, either side can be edited. When an
              AutoCount document disagrees with what we published, neither side wins
              automatically: the difference is held here until somebody answers it line by
              line. The sales order cannot be amended until they do.
            </InfoHint>
          </span>
        }
      />

      <DataGrid
        table={table}
        recordCount={divergences.data?.total ?? 0}
        isLoading={divergences.isLoading}
        listingKey="projects.projects.view::project-so-divergences"
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
                    placeholder="Search project or document number"
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
                  <div className="space-y-1.5">
                    <p className="text-sm font-medium">State</p>
                    <SearchableSelect
                      value={statusFilter}
                      onChange={(value) => {
                        setStatusFilter(value);
                        setPagination((current) => ({ ...current, pageIndex: 0 }));
                      }}
                      options={STATUS_OPTIONS}
                    />
                  </div>
                ),
              }}
              onRefresh={async () => {
                await divergences.refetch();
              }}
              isRefreshing={divergences.isFetching}
            />
          </CardHeader>

          <CardTable>
            {divergences.isError ? (
              <div className="px-6 py-10 text-center">
                <h3 className="text-sm font-semibold text-destructive">
                  The differences could not be loaded
                </h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  {divergences.error instanceof Error
                    ? divergences.error.message
                    : 'Try again in a moment.'}
                </p>
              </div>
            ) : !divergences.isLoading && rows.length === 0 ? (
              <div className="px-6 py-10 text-center">
                <CheckCircle2 className="mx-auto size-6 text-muted-foreground" aria-hidden />
                {/* "Reconciled" and "still to reconcile" are opposite facts, so one
                    sentence cannot be true of both empty states. */}
                <h3 className="mt-2 text-sm font-semibold">
                  {statusFilter === 'resolved'
                    ? 'Nothing has been reconciled yet'
                    : 'AutoCount agrees with every published sales order'}
                </h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  {statusFilter === 'resolved'
                    ? 'Answered reconciliations appear here, with who decided each row and why.'
                    : 'A difference appears here when an AutoCount export is read back against a sales order we published. Upload one from the sales order itself.'}
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

          {(divergences.data?.total ?? 0) > pagination.pageSize && (
            <CardFooter>
              <DataGridPagination />
            </CardFooter>
          )}
        </Card>
      </DataGrid>
    </>
  );
}
