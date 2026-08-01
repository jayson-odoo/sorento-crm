'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
  type ColumnDef,
  type PaginationState,
  type SortingState,
} from '@tanstack/react-table';
import { AlertCircle, FileUp, ScanLine, Search, Trash2 } from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

import type { FlyerReadingSummary } from '../../services/flyerReadingService';
import { deleteFlyerReading } from '../../services/flyerReadingService';
import { FLYER_READINGS_QUERY_KEY, useFlyerReadingsQuery } from '../hooks/useFlyerReadings';
import { UploadFlyerDialog } from './UploadFlyerDialog';

/**
 * Which flyers have been read.
 *
 * No report per row, deliberately: a report is a match run against 998 codes,
 * and one per row would make a screen whose only job is "which flyers exist"
 * cost a match run per flyer. The report lives on the review screen, where
 * somebody is actually reading it.
 *
 * Deleting a reading throws away the READING, never the brochure it seeded: a
 * page is its own row with its own versions, and nothing links the two. The
 * confirmation says so, because "delete" next to a flyer that produced a live
 * catalogue reads like it takes the catalogue with it.
 */
export function FlyerReadingsList() {
  const router = useRouter();
  const [search, setSearch] = useState('');
  const [uploadOpen, setUploadOpen] = useState(false);
  const [deleting, setDeleting] = useState<FlyerReadingSummary | null>(null);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 10 });

  const { data, isLoading, isError, error } = useFlyerReadingsQuery();

  const rows = useMemo(() => {
    const all = data ?? [];
    if (!search.trim()) return all;
    const needle = search.trim().toLowerCase();
    return all.filter((row) => row.filename.toLowerCase().includes(needle));
  }, [data, search]);

  const columns = useMemo<ColumnDef<FlyerReadingSummary>[]>(
    () => [
      {
        accessorKey: 'filename',
        header: ({ column }) => <DataGridColumnHeader title="Flyer" column={column} />,
        cell: ({ row }) => (
          <div className="truncate font-medium" title={row.original.filename}>
            {row.original.filename}
          </div>
        ),
        size: 360,
        minSize: 180,
        meta: { headerTitle: 'Flyer', skeleton: <Skeleton className="h-4 w-48" /> },
      },
      {
        accessorKey: 'pageCount',
        header: ({ column }) => <DataGridColumnHeader title="Pages" column={column} />,
        cell: ({ row }) => <span className="text-sm">{row.original.pageCount}</span>,
        size: 100,
        minSize: 80,
        meta: { headerTitle: 'Pages', skeleton: <Skeleton className="h-4 w-8" /> },
      },
      {
        accessorKey: 'codeCount',
        header: ({ column }) => <DataGridColumnHeader title="Product codes" column={column} />,
        cell: ({ row }) => <span className="text-sm">{row.original.codeCount}</span>,
        size: 140,
        minSize: 100,
        meta: { headerTitle: 'Product codes', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        accessorKey: 'uploadedAt',
        header: ({ column }) => <DataGridColumnHeader title="Read" column={column} />,
        cell: ({ row }) => (
          <span
            className="truncate text-sm text-muted-foreground"
            title={formatDateTimeInMalaysia(row.original.uploadedAt)}
          >
            {formatDateTimeInMalaysia(row.original.uploadedAt)}
          </span>
        ),
        size: 190,
        minSize: 130,
        meta: { headerTitle: 'Read', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        id: 'actions',
        header: '',
        cell: ({ row }) => (
          <div className="flex justify-end">
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Delete ${row.original.filename}`}
              onClick={(event) => {
                // The row opens the review screen, so the action must not
                // navigate on its way to the confirmation.
                event.stopPropagation();
                setDeleting(row.original);
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
      <Alert variant="destructive" data-testid="dk-fr-list-error">
        <AlertCircle className="size-4" />
        <AlertTitle>Could not load the flyers</AlertTitle>
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
      onRowClick={(row: FlyerReadingSummary) =>
        router.push(`/dealer-kit/flyer-readings/${row.id}`)
      }
      standardToolbar={false}
      // Explicit and stable, prefixed with the permission that guards the
      // screen. The default would key saved column widths on the pathname,
      // which is fine here but drifts the moment the route moves.
      listingKey="dealer_kit.page.view::flyer-readings"
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      emptyMessage={
        <div className="py-8 text-center" data-testid="dk-fr-list-empty">
          <ScanLine className="mx-auto size-6 text-muted-foreground" />
          <p className="mt-3 text-sm font-medium text-foreground">
            {search ? 'No flyer matches that search' : 'No flyer has been read yet'}
          </p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            {search
              ? 'Try part of the file name.'
              : 'Upload a printed flyer as a PDF. The product codes on it are matched against the master, and you review what was found before any brochure is created.'}
          </p>
          {!search && (
            <Button className="mt-4" size="sm" onClick={() => setUploadOpen(true)}>
              <FileUp className="size-4" />
              Read a flyer
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
                id="dk-fr-search"
                className="ps-9"
                placeholder="Search flyers"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                aria-label="Search flyers"
              />
            </div>
            <Button size="sm" className="shrink-0" onClick={() => setUploadOpen(true)}>
              <FileUp className="size-4" />
              Read a flyer
            </Button>
          </div>
        </CardHeader>

        <CardTable>
          {/* Wider than a phone, so it scrolls in its own container rather than
              dragging the page body sideways. */}
          <ScrollArea>
            <DataGridTable />
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </CardTable>

        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>

      <UploadFlyerDialog open={uploadOpen} onOpenChange={setUploadOpen} />

      <ConfirmDeleteDialog
        open={!!deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        title="Confirm delete"
        description={
          <>
            Delete the reading of <strong>{deleting?.filename}</strong>? Any brochure it already
            seeded is left exactly as it is. This action cannot be undone.
          </>
        }
        successMessage="Flyer reading deleted"
        queryKeysToInvalidate={[[FLYER_READINGS_QUERY_KEY]]}
        onDelete={async () => {
          if (deleting) await deleteFlyerReading(deleting.id);
        }}
      />
    </DataGrid>
  );
}
