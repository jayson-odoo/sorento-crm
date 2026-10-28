'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
  type ColumnDef,
  type PaginationState,
  type SortingState,
} from '@tanstack/react-table';
import { AlertCircle, Plus, Rotate3d, Trash2 } from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Skeleton } from '@/components/ui/skeleton';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useDeferredRowAction, useRowPending } from '@/hooks/useDeferredRowAction';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';

import type { WalkthroughSummary } from '../../services/walkthroughService';
import {
  WALKTHROUGHS_QUERY_KEY,
  useCreateWalkthrough,
  useWalkthroughsQuery,
} from '../hooks/useWalkthroughs';
import { WalkthroughNameDialog } from './WalkthroughNameDialog';

export function WalkthroughsList() {
  const router = useRouter();
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: search,
  } = useDebouncedSearch();
  const [createOpen, setCreateOpen] = useState(false);
  const create = useCreateWalkthrough();
  // Delete asks nothing (D7): the row dims and a countdown offers Cancel.
  const deletion = useDeferredRowAction({
    actionKey: 'dk_walkthrough.delete',
    entityType: 'dk_walkthrough',
    successMessage: 'Walkthrough deleted',
    invalidateKeys: [[WALKTHROUGHS_QUERY_KEY]],
  });
  const rowPending = useRowPending<WalkthroughSummary>('dk_walkthrough');
  const [sorting, setSorting] = useState<SortingState>([]);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 10 });

  const { data, isLoading, isError, error } = useWalkthroughsQuery();

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const all = data ?? [];
    return needle ? all.filter((row) => row.name.toLowerCase().includes(needle)) : all;
  }, [data, search]);

  const columns = useMemo<ColumnDef<WalkthroughSummary>[]>(
    () => [
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Walkthrough" column={column} />,
        cell: ({ row }) => (
          <div className="truncate font-medium" title={row.original.name}>
            {row.original.name}
          </div>
        ),
        size: 360,
        minSize: 180,
        meta: { headerTitle: 'Walkthrough', skeleton: <Skeleton className="h-4 w-48" /> },
      },
      {
        accessorKey: 'stopCount',
        header: ({ column }) => <DataGridColumnHeader title="Stops" column={column} />,
        cell: ({ row }) => <span className="text-sm">{row.original.stopCount}</span>,
        size: 100,
        minSize: 80,
        meta: { headerTitle: 'Stops', skeleton: <Skeleton className="h-4 w-8" /> },
      },
      {
        id: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => {
          const building = row.original.processingCount;
          return (
            <span
              className={`${STATUS_PILL_BASE} ${statusPillClass(building ? 'processing' : 'done')}`}
              data-testid="dk-wt-status-pill"
            >
              {building ? `Building ${building}` : 'Ready'}
            </span>
          );
        },
        size: 150,
        minSize: 110,
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'updatedAt',
        header: ({ column }) => <DataGridColumnHeader title="Updated" column={column} />,
        cell: ({ row }) => (
          <span
            className="truncate text-sm text-muted-foreground"
            title={formatDateTimeInMalaysia(row.original.updatedAt)}
          >
            {formatDateTimeInMalaysia(row.original.updatedAt)}
          </span>
        ),
        size: 190,
        minSize: 130,
        meta: { headerTitle: 'Updated', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        id: 'actions',
        header: '',
        cell: ({ row }) => (
          <div className="flex justify-end">
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Delete ${row.original.name}`}
              onClick={(event) => {
                event.stopPropagation();
                deletion.run({ id: row.original.id, subject: row.original.name });
              }}
            >
              <Trash2 className="size-4 text-destructive" />
            </Button>
          </div>
        ),
        size: 70,
        minSize: 70,
        enableResizing: false,
        meta: { headerTitle: 'Actions', skeleton: <Skeleton className="h-4 w-6" /> },
      },
    ],
    [deletion],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  if (isError) {
    return (
      <Alert variant="destructive" data-testid="dk-wt-list-error">
        <AlertCircle className="size-4" />
        <AlertTitle>Could not load the walkthroughs</AlertTitle>
        <AlertDescription>
          {error instanceof Error ? error.message : 'Something went wrong. Try again.'}
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <DataGrid
      table={table}
      recordCount={rows.length}
      isLoading={isLoading}
      onRowClick={(row: WalkthroughSummary) => router.push(`/dealer-kit/walkthroughs/${row.id}`)}
      rowPending={rowPending}
      standardToolbar={false}
      listingKey="dealer_kit.page.view::walkthroughs"
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      emptyMessage={
        <div className="py-8 text-center" data-testid="dk-wt-list-empty">
          <Rotate3d className="mx-auto size-6 text-muted-foreground" />
          <p className="mt-3 text-sm font-medium text-foreground">
            {search ? 'No walkthrough matches that search' : 'No walkthrough yet'}
          </p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            {search ? 'Try part of the name.' : 'Create one, then add a stop for each spot in the showroom.'}
          </p>
        </div>
      }
    >
      <Card>
        <CardHeader className="block py-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <ListSearchInput
              id="dk-wt-search"
              value={searchInput}
              onChange={setSearchInput}
              placeholder="Search walkthroughs"
              aria-label="Search walkthroughs"
              className="w-full sm:max-w-xs"
            />
            <Button size="sm" className="shrink-0" onClick={() => setCreateOpen(true)}>
              <Plus className="size-4" />
              New walkthrough
            </Button>
          </div>
        </CardHeader>

        <CardTable>
          <DataGridTable />
        </CardTable>

        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>

      <WalkthroughNameDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        title="New walkthrough"
        submitLabel="Create"
        isPending={create.isPending}
        onSubmit={(name) =>
          create.mutate(name, {
            onSuccess: (walkthrough) => {
              setCreateOpen(false);
              router.push(`/dealer-kit/walkthroughs/${walkthrough.id}`);
            },
          })
        }
      />
    </DataGrid>
  );
}
