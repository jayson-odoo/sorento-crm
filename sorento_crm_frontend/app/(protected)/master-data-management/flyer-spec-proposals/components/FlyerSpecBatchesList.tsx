'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type PaginationState,
  type SortingState,
} from '@tanstack/react-table';
import { AlertCircle, ScanLine, Search } from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';

import { useFlyerSpecBatchesQuery } from '../hooks/useFlyerSpecProposals';
import type { FlyerSpecBatch } from '../services/flyerSpecProposalService';

/**
 * Every flyer that has been read for specifications, and what came of it.
 *
 * The list exists so a merchandiser finds their batch without walking back
 * through the Dealer Kit: proposing happens over there, because that is where
 * the flyer is, but reviewing what a flyer says about the product master is
 * master-data work and belongs beside the specifications it changes.
 *
 * `Applied` is shown as a status of its own rather than as a date column nobody
 * scans, because "have these values been written yet" is the single question
 * this list is opened to answer.
 */

/** What a batch is called on screen, with `applied` derived from the counts. */
function statusOf(batch: FlyerSpecBatch): { key: string; label: string } {
  if (batch.status === 'proposing')
    return { key: 'processing', label: 'Proposing' };
  if (batch.status === 'failed') return { key: 'failed', label: 'Failed' };
  if (batch.applied_count > 0) return { key: 'done', label: 'Applied' };
  return { key: 'submitted', label: 'Proposed' };
}

/** A count column, all of them the same shape so the row reads as a row of figures. */
function figure(
  id: keyof FlyerSpecBatch,
  title: string,
  width: number,
): ColumnDef<FlyerSpecBatch> {
  return {
    id,
    header: ({ column }) => (
      <DataGridColumnHeader title={title} column={column} />
    ),
    cell: ({ row }) => (
      <span className="text-sm">{row.original[id] as number}</span>
    ),
    size: width,
    minSize: 70,
    enableSorting: false,
    meta: { headerTitle: title, skeleton: <Skeleton className="h-4 w-8" /> },
  };
}

function stamp(value: string | null): string {
  return value ? formatDateTimeInMalaysia(value) : 'Not yet';
}

export function FlyerSpecBatchesList() {
  const router = useRouter();
  const [search, setSearch] = useState('');
  const [sorting, setSorting] = useState<SortingState>([]);
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 10,
  });

  const { data, isLoading, isError, error } = useFlyerSpecBatchesQuery();

  const rows = useMemo(() => {
    const all = data ?? [];
    if (!search.trim()) return all;
    const needle = search.trim().toLowerCase();
    return all.filter((row) => row.filename.toLowerCase().includes(needle));
  }, [data, search]);

  const columns = useMemo<ColumnDef<FlyerSpecBatch>[]>(
    () => [
      {
        accessorKey: 'filename',
        header: ({ column }) => (
          <DataGridColumnHeader title="Flyer" column={column} />
        ),
        cell: ({ row }) => (
          <div className="truncate font-medium" title={row.original.filename}>
            {row.original.filename}
          </div>
        ),
        size: 300,
        minSize: 160,
        meta: {
          headerTitle: 'Flyer',
          skeleton: <Skeleton className="h-4 w-48" />,
        },
      },
      {
        accessorKey: 'status',
        header: ({ column }) => (
          <DataGridColumnHeader title="Status" column={column} />
        ),
        cell: ({ row }) => {
          const status = statusOf(row.original);
          return (
            <div className="flex min-w-0 items-center gap-2">
              <span
                className={`${STATUS_PILL_BASE} shrink-0 ${statusPillClass(status.key)}`}
                data-testid="fsp-status-pill"
              >
                {status.label}
              </span>
              {row.original.status === 'failed' &&
                row.original.error_message && (
                  <span
                    className="truncate text-xs text-muted-foreground"
                    title={row.original.error_message}
                  >
                    {row.original.error_message}
                  </span>
                )}
            </div>
          );
        },
        size: 240,
        minSize: 120,
        meta: {
          headerTitle: 'Status',
          skeleton: <Skeleton className="h-4 w-20" />,
        },
      },
      figure('product_count', 'Products', 110),
      figure('proposal_count', 'Values', 100),
      figure('new_count', 'New', 90),
      figure('change_count', 'Change', 100),
      figure('conflict_count', 'Conflict', 100),
      {
        accessorKey: 'read_at',
        header: ({ column }) => (
          <DataGridColumnHeader title="Read on" column={column} />
        ),
        cell: ({ row }) => (
          <span
            className="truncate text-sm text-muted-foreground"
            title={stamp(row.original.read_at)}
          >
            {stamp(row.original.read_at)}
          </span>
        ),
        size: 180,
        minSize: 130,
        meta: {
          headerTitle: 'Read on',
          skeleton: <Skeleton className="h-4 w-28" />,
        },
      },
      {
        accessorKey: 'finished_at',
        header: ({ column }) => (
          <DataGridColumnHeader title="Proposed on" column={column} />
        ),
        cell: ({ row }) => (
          <span
            className="truncate text-sm text-muted-foreground"
            title={stamp(row.original.finished_at)}
          >
            {stamp(row.original.finished_at)}
          </span>
        ),
        size: 180,
        minSize: 130,
        meta: {
          headerTitle: 'Proposed on',
          skeleton: <Skeleton className="h-4 w-28" />,
        },
      },
      {
        accessorKey: 'applied_at',
        header: ({ column }) => (
          <DataGridColumnHeader title="Applied on" column={column} />
        ),
        cell: ({ row }) => (
          <span
            className="truncate text-sm text-muted-foreground"
            title={stamp(row.original.applied_at)}
          >
            {stamp(row.original.applied_at)}
          </span>
        ),
        size: 180,
        minSize: 130,
        meta: {
          headerTitle: 'Applied on',
          skeleton: <Skeleton className="h-4 w-28" />,
        },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.reading_id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    // Without this the headers offer a sort the table never performs: the arrow
    // toggles, `sorting` updates, and the rows sit exactly where they were.
    getSortedRowModel: getSortedRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  if (isError) {
    return (
      <Alert variant="destructive" data-testid="fsp-list-error">
        <AlertCircle className="size-4" />
        <AlertTitle>Could not load the flyer proposals</AlertTitle>
        <AlertDescription>
          {error instanceof Error
            ? error.message
            : 'Something went wrong. Try again.'}
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <DataGrid
      table={table}
      recordCount={rows.length}
      isLoading={isLoading}
      onRowClick={(row: FlyerSpecBatch) =>
        router.push(
          `/master-data-management/flyer-spec-proposals/${row.reading_id}`,
        )
      }
      standardToolbar={false}
      listingKey="master_data.products.edit::flyer-spec-proposals"
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      emptyMessage={
        <div className="py-8 text-center" data-testid="fsp-list-empty">
          <ScanLine className="mx-auto size-6 text-muted-foreground" />
          <p className="mt-3 text-sm font-medium text-foreground">
            {search
              ? 'No flyer matches that search'
              : 'No flyer has been proposed yet'}
          </p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            {search
              ? 'Try part of the file name.'
              : 'Read a flyer in Dealer Kit and press Propose specs.'}
          </p>
        </div>
      }
    >
      <Card>
        <CardHeader className="block py-5">
          <div className="relative w-full sm:max-w-xs">
            <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="fsp-search"
              className="ps-9"
              placeholder="Search flyers"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              aria-label="Search flyers"
            />
          </div>
        </CardHeader>

        <CardTable>
          {/* Ten columns is wider than a phone, so it scrolls in its own
              container rather than dragging the page sideways. */}
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
