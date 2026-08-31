'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
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
import { AlertCircle, FileText, Plus, Trash2 } from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import {
  useDeferredRowAction,
  useRowPending,
} from '@/hooks/useDeferredRowAction';
import { Skeleton } from '@/components/ui/skeleton';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { listPages } from '../services/dealerKitService';
import { NewPageDialog } from './NewPageDialog';
import type { PageSummary } from '@/lib/dealer-kit/types';

export function PagesList() {
  const router = useRouter();
  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: search,
  } = useDebouncedSearch();
  const [newOpen, setNewOpen] = useState(false);
  // Delete asks nothing (D7): the row dims and a toast counts down with Cancel.
  const deletion = useDeferredRowAction({
    actionKey: 'dk_page.delete',
    entityType: 'dk_page',
    successMessage: 'Page deleted',
    invalidateKeys: [['dealer-kit', 'pages']],
  });
  const rowPending = useRowPending<PageSummary>('dk_page');
  const [sorting, setSorting] = useState<SortingState>([]);
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 10,
  });

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['dealer-kit', 'pages'],
    queryFn: listPages,
  });

  const rows = useMemo(() => {
    const all = data ?? [];
    if (!search.trim()) return all;

    const needle = search.trim().toLowerCase();
    return all.filter(
      (page) =>
        page.name.toLowerCase().includes(needle) || page.slug.toLowerCase().includes(needle),
    );
  }, [data, search]);

  const columns = useMemo<ColumnDef<PageSummary>[]>(
    () => [
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Page" column={column} />,
        cell: ({ row }) => (
          <div className="truncate font-medium" title={row.original.name}>
            {row.original.name}
          </div>
        ),
        size: 280,
        minSize: 160,
        meta: { headerTitle: 'Page', skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        accessorKey: 'slug',
        header: ({ column }) => <DataGridColumnHeader title="Address" column={column} />,
        cell: ({ row }) => {
          // The backend resolves this, company segment included. Guessing it
          // here would print an address that does not resolve.
          const path = row.original.publicPath ?? `/${row.original.slug}`;
          return (
            <div className="truncate font-mono text-xs text-muted-foreground" title={path}>
              {path}
            </div>
          );
        },
        size: 200,
        minSize: 120,
        meta: { headerTitle: 'Address', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        id: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) =>
          row.original.publishedVersion === null ? (
            <Badge variant="outline" className="font-normal">
              Not published
            </Badge>
          ) : (
            <Badge variant="success" className="font-normal">
              Live · v{row.original.publishedVersion}
            </Badge>
          ),
        size: 150,
        minSize: 110,
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        accessorKey: 'latestVersion',
        header: ({ column }) => <DataGridColumnHeader title="Latest draft" column={column} />,
        cell: ({ row }) => <span className="text-sm">v{row.original.latestVersion}</span>,
        size: 120,
        minSize: 90,
        meta: { headerTitle: 'Latest draft', skeleton: <Skeleton className="h-4 w-12" /> },
      },
      {
        accessorKey: 'updatedAt',
        header: ({ column }) => <DataGridColumnHeader title="Last edited" column={column} />,
        cell: ({ row }) => (
          <span className="truncate text-sm text-muted-foreground">
            {formatDateTimeInMalaysia(row.original.updatedAt)}
          </span>
        ),
        size: 180,
        minSize: 130,
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
              aria-label={`Delete ${row.original.name}`}
              onClick={(event) => {
                // The row itself opens the editor, so the action must not
                // navigate on its way to parking the delete.
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
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  if (isError) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="size-4" />
        <AlertTitle>Could not load pages</AlertTitle>
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
      onRowClick={(row: PageSummary) => router.push(`/dealer-kit/pages/${row.id}`)}
      rowPending={rowPending}
      standardToolbar={false}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      emptyMessage={
        <div className="py-8 text-center">
          <FileText className="mx-auto size-6 text-muted-foreground" />
          <p className="mt-3 text-sm font-medium text-foreground">
            {search ? 'No pages match that search' : 'No catalogue pages yet'}
          </p>
          <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
            {search
              ? 'Try a different name or address.'
              : 'A page is one publishable catalogue. Create one to start laying out sections and binding products to it.'}
          </p>
          {!search && (
            <Button className="mt-4" size="sm" onClick={() => setNewOpen(true)}>
              <Plus className="size-4" />
              New page
            </Button>
          )}
        </div>
      }
    >
      <Card>
        <CardHeader className="block py-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <ListSearchInput
              value={searchInput}
              onChange={setSearchInput}
              placeholder="Search pages"
              aria-label="Search pages"
              className="w-full sm:max-w-xs"
            />
            <Button size="sm" className="shrink-0" onClick={() => setNewOpen(true)}>
              <Plus className="size-4" />
              New page
            </Button>
          </div>
        </CardHeader>

        <CardTable>
          {/* The table is wider than a phone. It scrolls inside its own
              container so the page body never scrolls sideways. */}
          <DataGridTable />
        </CardTable>

        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>

      <NewPageDialog open={newOpen} onOpenChange={setNewOpen} />

    </DataGrid>
  );
}
