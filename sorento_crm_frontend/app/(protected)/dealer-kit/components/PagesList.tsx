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
import { AlertCircle, FileText, Plus, Search } from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { listPages } from '../services/dealerKitService';
import type { PageSummary } from '@/lib/dealer-kit/types';

export function PagesList() {
  const router = useRouter();
  const [search, setSearch] = useState('');
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
        cell: ({ row }) => (
          <div className="truncate font-mono text-xs text-muted-foreground" title={`/c/${row.original.slug}`}>
            /c/{row.original.slug}
          </div>
        ),
        size: 200,
        minSize: 120,
        meta: { headerTitle: 'Address', skeleton: <Skeleton className="h-4 w-28" /> },
      },
      {
        id: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) =>
          row.original.publishedVersion === null ? (
            <Badge variant="outline" appearance="ghost" className="font-normal">
              Not published
            </Badge>
          ) : (
            <Badge variant="success" appearance="ghost" className="font-normal">
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
    ],
    [],
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
            <Button className="mt-4" size="sm">
              <Plus className="size-4" />
              New page
            </Button>
          )}
        </div>
      }
    >
      <Card>
        <CardHeader className="block">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative w-full sm:max-w-xs">
              <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                className="ps-9"
                placeholder="Search pages"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                aria-label="Search pages"
              />
            </div>
            <Button size="sm" className="shrink-0">
              <Plus className="size-4" />
              New page
            </Button>
          </div>
        </CardHeader>

        <CardTable>
          {/* The table is wider than a phone. It scrolls inside its own
              container so the page body never scrolls sideways. */}
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
