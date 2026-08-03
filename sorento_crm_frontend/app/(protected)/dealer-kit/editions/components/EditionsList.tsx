'use client';

import { useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
  type ColumnDef,
  type PaginationState,
  type SortingState,
} from '@tanstack/react-table';
import { AlertCircle, Plus, Search } from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

import type { Edition } from '../../services/editionService';
import { useCreateEdition, useEditionsQuery } from '../hooks/useEditions';

/**
 * The approval queue.
 *
 * Newest first and unfiltered by default: an Approver wants the ones waiting on
 * them, and a Designer wants the one they were sent back. Both are near the top
 * of the same list, so a status filter would be a control most people set once
 * and then forget is set.
 */
export function EditionsList() {
  const router = useRouter();
  // Narrowed to one catalogue when arrived at from that catalogue's gear.
  // Without it this is the whole queue, which is what an Approver wants.
  const pageId = useSearchParams().get('pageId') ?? undefined;
  const [search, setSearch] = useState('');
  const [startOpen, setStartOpen] = useState(false);
  const [name, setName] = useState('');
  const [sorting, setSorting] = useState<SortingState>([]);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 10 });

  const { data, isLoading, isError, error } = useEditionsQuery(pageId);
  const create = useCreateEdition();

  const rows = useMemo(() => {
    const all = data ?? [];
    const needle = search.trim().toLowerCase();
    if (!needle) return all;
    return all.filter(
      (row) =>
        row.name.toLowerCase().includes(needle) ||
        (row.pageName ?? '').toLowerCase().includes(needle),
    );
  }, [data, search]);

  const columns = useMemo<ColumnDef<Edition>[]>(
    () => [
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Edition" column={column} />,
        cell: ({ row }) => (
          <div className="truncate font-medium" title={row.original.name}>
            {row.original.name}
          </div>
        ),
        size: 260,
        minSize: 140,
        meta: { headerTitle: 'Edition' },
      },
      {
        id: 'catalogue',
        header: ({ column }) => <DataGridColumnHeader title="Catalogue" column={column} />,
        cell: ({ row }) => (
          <div className="truncate text-muted-foreground" title={row.original.pageName ?? ''}>
            {row.original.pageName ?? '-'}
          </div>
        ),
        size: 260,
        minSize: 140,
        meta: { headerTitle: 'Catalogue' },
      },
      {
        id: 'status',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => (
          <span className={`${STATUS_PILL_BASE} ${statusPillClass(row.original.status)}`}>
            {row.original.statusLabel}
          </span>
        ),
        size: 160,
        minSize: 120,
        meta: { headerTitle: 'Status' },
      },
      {
        id: 'submittedAt',
        header: ({ column }) => <DataGridColumnHeader title="Sent for approval" column={column} />,
        cell: ({ row }) => (
          <span className="truncate text-sm text-muted-foreground">
            {row.original.submittedAt
              ? formatDateTimeInMalaysia(row.original.submittedAt)
              : '-'}
          </span>
        ),
        size: 200,
        minSize: 140,
        meta: { headerTitle: 'Sent for approval' },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    state: { sorting, pagination },
    onSortingChange: setSorting,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  if (isLoading) {
    return <Skeleton className="h-64 w-full" />;
  }

  if (isError) {
    return (
      <Alert variant="destructive" data-testid="dk-ed-error">
        <AlertCircle className="size-4" />
        <AlertTitle>Could not load editions</AlertTitle>
        <AlertDescription>
          {error instanceof Error ? error.message : 'Try again in a moment.'}
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <DataGrid
      table={table}
      recordCount={rows.length}
      isLoading={isLoading}
      standardToolbar={false}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      // Prefixed with the permission that guards the screen. The default keys
      // saved column widths on the pathname, which drifts if the route moves.
      listingKey="dealer_kit.page.view::editions"
      onRowClick={(row) => router.push(`/dealer-kit/editions/${row.id}`)}
      emptyMessage={
        <div className="py-8 text-center" data-testid="dk-ed-list-empty">
          <p className="text-sm font-medium text-foreground">
            {search ? 'No edition matches that search' : 'No editions yet'}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {search ? 'Try part of the catalogue name.' : 'Start one from a catalogue page.'}
          </p>
        </div>
      }
    >
      <Card>
        <CardHeader className="flex-wrap gap-2 py-4">
          <div className="relative w-full sm:w-72">
            <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="dk-ed-search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Edition or catalogue"
              className="ps-9"
            />
          </div>
          {/* Only when a catalogue is in scope. An Edition belongs to one page,
              so the whole-queue view has nothing to start one against. */}
          {pageId && (
            <Button
              size="sm"
              onClick={() => {
                setName('');
                setStartOpen(true);
              }}
            >
              <Plus className="size-4" />
              Start an edition
            </Button>
          )}
        </CardHeader>
        <CardTable>
          <ScrollArea>
            <DataGridTable />
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </CardTable>
        <CardFooter>
          <DataGridPagination />
        </CardFooter>
      </Card>

      <Dialog open={startOpen} onOpenChange={setStartOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Start an edition</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor="dk-ed-name">Name</Label>
            <Input
              id="dk-ed-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Spring 2027"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setStartOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={!name.trim() || create.isPending}
              onClick={() =>
                pageId &&
                create.mutate(
                  { pageId, name: name.trim() },
                  {
                    onSuccess: (edition) => {
                      setStartOpen(false);
                      router.push(`/dealer-kit/editions/${edition.id}`);
                    },
                  },
                )
              }
            >
              {create.isPending ? 'Starting' : 'Start'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </DataGrid>
  );
}
