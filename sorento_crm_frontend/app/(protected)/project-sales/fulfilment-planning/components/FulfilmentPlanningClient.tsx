'use client';

import * as React from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import {
  ColumnDef,
  PaginationState,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { PackageSearch, Search, X } from 'lucide-react';
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
import { useFulfilmentPlanning } from '../../_shared/hooks/useFulfilmentPlanning';
import { ReviewStatePill } from '../../_shared/components/ReviewStatePill';
import type {
  FulfilmentPlanningRow,
  ReviewState,
} from '../../_shared/types/fulfilmentPlanning.types';
import { REVIEW_STATE_LABELS } from '../../_shared/types/fulfilmentPlanning.types';
import { InfoHint } from '../../[projectId]/components/InfoHint';
import { FulfilmentPlanningSheet } from './FulfilmentPlanningSheet';

const REVIEW_STATE_OPTIONS = [
  { value: 'all', label: 'Any' },
  {
    value: 'awaiting_reconciliation',
    label: REVIEW_STATE_LABELS.awaiting_reconciliation,
  },
  { value: 'needs_cs_review', label: REVIEW_STATE_LABELS.needs_cs_review },
];

/**
 * Every published or amended Project SO across projects, one row each (journey step 1).
 *
 * The screen is a worklist rather than a report: the review state and the exception count
 * are what a CS reads down the page, and the row is the way into the reconciliation for
 * that order. Nothing here is per line - the whole sales order carries one state (AC-A03),
 * so no column can say "3 of 4 lines confirmed".
 *
 * `?mock=empty` and `?mock=error` reach the empty and failed list while the Phase 1
 * fixtures are serving (`NEXT_PUBLIC_PROJECT_SO_MOCK=1`). The param is inert against the
 * real service and goes when the fixtures do.
 */
export function FulfilmentPlanningClient() {
  const searchParams = useSearchParams();
  const mockCase = searchParams?.get('mock') ?? undefined;

  const [reviewState, setReviewState] = React.useState('all');
  const [search, setSearch] = React.useState('');
  const [openRow, setOpenRow] = React.useState<FulfilmentPlanningRow | null>(null);
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });

  const planning = useFulfilmentPlanning({
    page: pagination.pageIndex + 1,
    limit: pagination.pageSize,
    query: search.trim() || undefined,
    review_state: reviewState === 'all' ? undefined : (reviewState as ReviewState),
    mock_case: mockCase,
  });

  const rows = React.useMemo(() => planning.data?.data ?? [], [planning.data]);

  // Column order is the reading order of the worklist: which sales order, which document,
  // what state it is in, how far the mapping got. The rest is context and can sit past the
  // fold, because a CS scanning the page is answering "what still needs work".
  const columns = React.useMemo<ColumnDef<FulfilmentPlanningRow>[]>(
    () => [
      {
        id: 'provisional_ref',
        header: ({ column }) => <DataGridColumnHeader title="Project SO" column={column} />,
        cell: ({ row }) => (
          <span
            className="block truncate font-medium tabular-nums"
            title={row.original.provisional_ref}
          >
            {row.original.provisional_ref}
          </span>
        ),
        size: 140,
        minSize: 110,
        meta: { headerTitle: 'Project SO', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'autocount_doc_no',
        header: ({ column }) => <DataGridColumnHeader title="AutoCount doc" column={column} />,
        cell: ({ row }) =>
          row.original.autocount_doc_no ? (
            <span className="block truncate tabular-nums" title={row.original.autocount_doc_no}>
              {row.original.autocount_doc_no}
            </span>
          ) : (
            <span className="text-muted-foreground">Not uploaded</span>
          ),
        size: 140,
        minSize: 110,
        meta: { headerTitle: 'AutoCount doc', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'review_state',
        header: ({ column }) => <DataGridColumnHeader title="Review state" column={column} />,
        cell: ({ row }) => (
          <ReviewStatePill
            state={row.original.review_state}
            exceptionCount={row.original.exception_count}
          />
        ),
        // Wide enough for the longest pill it can hold, "Awaiting reconciliation · 3
        // exceptions": the count is the instruction, and a truncated one is worse than none.
        size: 275,
        minSize: 200,
        meta: { headerTitle: 'Review state', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        id: 'lines',
        header: ({ column }) => <DataGridColumnHeader title="Lines" column={column} />,
        cell: ({ row }) => {
          const text = `${row.original.lines_linked} linked / ${row.original.line_count}`;
          return (
            <span className="block truncate tabular-nums" title={text}>
              {text}
            </span>
          );
        },
        size: 120,
        minSize: 105,
        meta: { headerTitle: 'Lines', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'project',
        header: ({ column }) => <DataGridColumnHeader title="Project" column={column} />,
        cell: ({ row }) => (
          <div className="flex min-w-0 flex-col gap-0.5">
            <span className="block truncate" title={row.original.project_name}>
              {row.original.project_name}
            </span>
            <span
              className="block truncate text-xs text-muted-foreground"
              title={row.original.project_code}
            >
              {row.original.project_code}
            </span>
          </div>
        ),
        size: 180,
        minSize: 140,
        meta: { headerTitle: 'Project', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        id: 'customer_name',
        header: ({ column }) => <DataGridColumnHeader title="Customer" column={column} />,
        cell: ({ row }) =>
          row.original.customer_name ? (
            <span className="block truncate" title={row.original.customer_name}>
              {row.original.customer_name}
            </span>
          ) : (
            <span className="text-muted-foreground">Not recorded</span>
          ),
        size: 180,
        minSize: 140,
        meta: { headerTitle: 'Customer', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        id: 'po_number',
        header: ({ column }) => <DataGridColumnHeader title="Customer PO" column={column} />,
        cell: ({ row }) =>
          row.original.po_number ? (
            <span className="block truncate" title={row.original.po_number}>
              {row.original.po_number}
            </span>
          ) : (
            <span className="text-muted-foreground">None</span>
          ),
        size: 130,
        minSize: 110,
        meta: { headerTitle: 'Customer PO', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'area_group',
        header: ({ column }) => <DataGridColumnHeader title="Area group" column={column} />,
        cell: ({ row }) =>
          row.original.area_group ? (
            <span className="block truncate" title={row.original.area_group}>
              {row.original.area_group}
            </span>
          ) : (
            <span className="text-muted-foreground">No area group</span>
          ),
        size: 130,
        minSize: 110,
        meta: { headerTitle: 'Area group', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'updated_at',
        header: ({ column }) => <DataGridColumnHeader title="Updated" column={column} />,
        cell: ({ row }) =>
          row.original.updated_at ? (
            <span className="block truncate tabular-nums">
              {formatDateInMalaysia(row.original.updated_at)}
            </span>
          ) : (
            <span className="text-muted-foreground">Unknown</span>
          ),
        size: 130,
        minSize: 100,
        meta: { headerTitle: 'Updated', skeleton: <Skeleton className="h-4 w-20" /> },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.ceil((planning.data?.total ?? 0) / pagination.pageSize) || 0,
    getRowId: (row) => row.id,
    state: { pagination },
    onPaginationChange: setPagination,
    manualPagination: true,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
  });

  const filtersActive = reviewState !== 'all' ? 1 : 0;

  return (
    <>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2">
          <h1 className="text-xl font-semibold break-words">Fulfilment planning</h1>
          <InfoHint label="About fulfilment planning">
            A published sales order is planned against the AutoCount document that carries
            it. Until every line of ours is matched to exactly one line of theirs, the order
            is awaiting reconciliation and nothing about it has been promised to purchasing.
          </InfoHint>
        </div>
      </div>

      <DataGrid
        table={table}
        recordCount={planning.data?.total ?? 0}
        isLoading={planning.isLoading}
        listingKey="projects.projects.view::project-fulfilment-planning"
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        onRowClick={(row) => setOpenRow(row)}
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
                    placeholder="Search sales order, project or customer"
                    value={search}
                    onChange={(event) => {
                      setSearch(event.target.value);
                      setPagination((current) => ({ ...current, pageIndex: 0 }));
                    }}
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
                    <p className="text-sm font-medium">Review state</p>
                    <SearchableSelect
                      value={reviewState}
                      onChange={(value) => {
                        setReviewState(value);
                        setPagination((current) => ({ ...current, pageIndex: 0 }));
                      }}
                      options={REVIEW_STATE_OPTIONS}
                    />
                  </div>
                ),
              }}
              onRefresh={async () => {
                await planning.refetch();
              }}
              isRefreshing={planning.isFetching}
            />
          </CardHeader>

          <CardTable>
            {planning.isError ? (
              <div className="px-6 py-10 text-center">
                <h3 className="text-sm font-semibold text-destructive">
                  The planning list could not be loaded
                </h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  {planning.error instanceof Error
                    ? planning.error.message
                    : 'Try again in a moment.'}
                </p>
                <Button
                  type="button"
                  variant="outline"
                  className="mt-4"
                  onClick={() => planning.refetch()}
                >
                  Try again
                </Button>
              </div>
            ) : !planning.isLoading && rows.length === 0 ? (
              <div className="px-6 py-10 text-center">
                <PackageSearch className="mx-auto size-6 text-muted-foreground" aria-hidden />
                <h3 className="mt-2 text-sm font-semibold">
                  {reviewState === 'needs_cs_review'
                    ? 'No sales order has finished reconciling yet'
                    : reviewState === 'awaiting_reconciliation'
                      ? 'Every sales order here is reconciled'
                      : 'No published Project SO yet'}
                </h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  {reviewState === 'all'
                    ? 'A sales order appears here once it is published from a project. Publish one from the project, then upload its AutoCount document.'
                    : 'Clear the review state filter to see the rest of the sales orders.'}
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

          {(planning.data?.total ?? 0) > pagination.pageSize && (
            <CardFooter>
              <DataGridPagination />
            </CardFooter>
          )}
        </Card>
      </DataGrid>

      <FulfilmentPlanningSheet
        row={openRow}
        open={Boolean(openRow)}
        onOpenChange={(next) => {
          if (!next) setOpenRow(null);
        }}
      />
    </>
  );
}
