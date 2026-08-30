'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
  type ColumnDef,
  type PaginationState,
  type SortingState,
} from '@tanstack/react-table';
import { AlertCircle, Layers, Plus, Search, Trash2 } from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import {
  useDeferredRowAction,
  useRowPending,
} from '@/hooks/useDeferredRowAction';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { listCollections } from '../../services/catalogueService';
import type { CollectionSummary } from '@/lib/dealer-kit/types';
import { CollectionDialog } from './CollectionDialog';

/**
 * The reusable collection library.
 *
 * Only `scope=library` rows appear. The page-scoped collections created when a
 * Designer picks products inside an editor are an implementation detail of that
 * page - listing them here would bury the handful of curated sets that are meant
 * to be reused under one row per page anyone ever edited (AC-F4).
 *
 * The point of a library collection is that binding it to several pages means
 * one edit reaches all of them (AC-F7), which is also why deleting one is worth
 * a confirmation: it is not scoped to the page you happen to be looking at.
 */
export function CollectionsList() {
  const [search, setSearch] = useState('');
  // Delete asks nothing (D7): the row dims and a toast counts down with Cancel.
  const deletion = useDeferredRowAction({
    actionKey: 'dk_collection.delete',
    entityType: 'dk_collection',
    successMessage: 'Collection deleted',
    invalidateKeys: [['dealer-kit', 'collections']],
  });
  const rowPending = useRowPending<CollectionSummary>('dk_collection');
  /**
   * The collection being edited, or `undefined` when the dialog is shut.
   *
   * `null` is a real value here - it means "a new one" - so absence has to be a
   * third state rather than being folded into null.
   */
  const [editing, setEditing] = useState<CollectionSummary | null | undefined>(undefined);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 10,
  });

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['dealer-kit', 'collections'],
    queryFn: listCollections,
  });

  const rows = useMemo(() => {
    const all = data ?? [];
    const needle = search.trim().toLowerCase();
    if (!needle) return all;
    return all.filter((row) => (row.name ?? '').toLowerCase().includes(needle));
  }, [data, search]);

  const columns = useMemo<ColumnDef<CollectionSummary>[]>(
    () => [
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Collection" column={column} />,
        cell: ({ row }) => (
          <div className="truncate font-medium" title={row.original.name ?? 'Untitled'}>
            {row.original.name ?? 'Untitled'}
          </div>
        ),
        size: 320,
        minSize: 180,
        meta: { headerTitle: 'Collection', skeleton: <Skeleton className="h-4 w-44" /> },
      },
      {
        accessorKey: 'memberCount',
        header: ({ column }) => <DataGridColumnHeader title="Products" column={column} />,
        cell: ({ row }) => (
          <Badge variant="outline" className="font-normal">
            {row.original.memberCount}
          </Badge>
        ),
        size: 120,
        minSize: 90,
        meta: { headerTitle: 'Products', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        accessorKey: 'updatedAt',
        header: ({ column }) => <DataGridColumnHeader title="Last edited" column={column} />,
        cell: ({ row }) => (
          <span className="truncate text-sm text-muted-foreground">
            {formatDateTimeInMalaysia(row.original.updatedAt)}
          </span>
        ),
        size: 200,
        minSize: 140,
        meta: { headerTitle: 'Last edited', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        id: 'actions',
        header: '',
        cell: ({ row }) => (
          <div className="flex justify-end">
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Delete ${row.original.name ?? 'collection'}`}
              onClick={() =>
                deletion.run({ id: row.original.id, subject: row.original.name ?? 'this collection' })
              }
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
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  if (isError) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="size-4" />
        <AlertTitle>Could not load collections</AlertTitle>
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
      rowPending={rowPending}
      standardToolbar={false}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      onRowClick={(row) => setEditing(row)}
      emptyMessage={
        <div className="py-8 text-center">
          <Layers className="mx-auto size-6 text-muted-foreground" />
          <p className="mt-3 text-sm font-medium text-foreground">
            {search ? 'No collections match that search' : 'No reusable collections yet'}
          </p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            {search
              ? 'Try a different name.'
              : 'Start one with the button above, or pick products inside a page and save that set here. Editing it once updates every page that uses it.'}
          </p>
        </div>
      }
    >
      <Card>
        <CardHeader className="flex-wrap gap-2 py-5">
          <div className="relative w-full sm:max-w-xs">
            <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="ps-9"
              placeholder="Search collections"
              aria-label="Search collections"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          {/* A collection could only be born inside a page editor, by picking
              products in a block and then promoting the result. That is a fine
              shortcut and a poor only-way-in: this is a list of records, and
              every other list in the system can create one. */}
          <Button size="sm" onClick={() => setEditing(null)}>
            <Plus className="size-4" />
            New collection
          </Button>
        </CardHeader>

        <CardTable>
          <DataGridTable />
        </CardTable>

        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>

      <CollectionDialog
        open={editing !== undefined}
        onOpenChange={(next) => !next && setEditing(undefined)}
        collection={editing ?? null}
      />

    </DataGrid>
  );
}
