'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
  type ColumnDef,
  type PaginationState,
} from '@tanstack/react-table';
import { AlertCircle, LayoutTemplate, Pencil, Plus, Search, Trash2 } from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import {
  TILE_FIELDS,
  deleteTileTemplate,
  listTileTemplates,
} from '../../services/catalogueService';
import { TileDesignDialog } from './TileDesignDialog';
import type { TileTemplate } from '@/lib/dealer-kit/types';

/**
 * Tile designs: what a single product's card shows.
 *
 * One design is authored once and bound by any number of collection blocks, so
 * changing it restyles every catalogue using it - which is the whole reason it
 * is a separate thing rather than settings on a block.
 */
export function TileDesignsList() {
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<TileTemplate | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState<TileTemplate | null>(null);
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 10,
  });

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['dealer-kit', 'tile-templates'],
    queryFn: listTileTemplates,
  });

  const rows = useMemo(() => {
    const all = data ?? [];
    const needle = search.trim().toLowerCase();
    if (!needle) return all;
    return all.filter((row) => row.name.toLowerCase().includes(needle));
  }, [data, search]);

  const columns = useMemo<ColumnDef<TileTemplate>[]>(
    () => [
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Design" column={column} />,
        cell: ({ row }) => (
          <div className="truncate font-medium" title={row.original.name}>
            {row.original.name}
          </div>
        ),
        size: 260,
        minSize: 160,
        meta: { headerTitle: 'Design', skeleton: <Skeleton className="h-4 w-40" /> },
      },
      {
        id: 'fields',
        header: ({ column }) => <DataGridColumnHeader title="Shows" column={column} />,
        cell: ({ row }) => (
          <div className="flex flex-wrap gap-1">
            {row.original.fields.map((field) => (
              <Badge key={field} variant="outline" appearance="ghost" className="text-xs">
                {TILE_FIELDS.find((candidate) => candidate.value === field)?.label ?? field}
              </Badge>
            ))}
          </div>
        ),
        size: 360,
        minSize: 200,
        meta: { headerTitle: 'Shows', skeleton: <Skeleton className="h-4 w-48" /> },
      },
      {
        accessorKey: 'updatedAt',
        header: ({ column }) => <DataGridColumnHeader title="Last edited" column={column} />,
        cell: ({ row }) => (
          <span className="truncate text-sm text-muted-foreground">
            {formatDateTimeInMalaysia(row.original.updatedAt)}
          </span>
        ),
        size: 190,
        minSize: 140,
        meta: { headerTitle: 'Last edited', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        id: 'actions',
        header: '',
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Edit ${row.original.name}`}
              onClick={() => {
                setEditing(row.original);
                setDialogOpen(true);
              }}
            >
              <Pencil className="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Delete ${row.original.name}`}
              onClick={() => setDeleting(row.original)}
            >
              <Trash2 className="size-4 text-destructive" />
            </Button>
          </div>
        ),
        size: 110,
        minSize: 110,
        enableResizing: false,
        meta: { headerTitle: 'Actions', skeleton: <Skeleton className="h-4 w-10" /> },
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    state: { pagination },
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  if (isError) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="size-4" />
        <AlertTitle>Could not load tile designs</AlertTitle>
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
      standardToolbar={false}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      emptyMessage={
        <div className="py-8 text-center">
          <LayoutTemplate className="mx-auto size-6 text-muted-foreground" />
          <p className="mt-3 text-sm font-medium text-foreground">
            {search.trim() ? 'No tile designs match that search' : 'No tile designs yet'}
          </p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            {search.trim()
              ? 'Try a different name.'
              : 'A tile design decides what each product card shows. Create one, then bind it to a products block on any page.'}
          </p>
          {!search.trim() && (
            <Button
              className="mt-4"
              size="sm"
              onClick={() => {
                setEditing(null);
                setDialogOpen(true);
              }}
            >
              <Plus className="size-4" />
              New design
            </Button>
          )}
        </div>
      }
    >
      <Card>
        <CardHeader className="flex-wrap gap-2 py-5">
          <div className="relative w-full sm:max-w-xs">
            <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="ps-9"
              placeholder="Search tile designs"
              aria-label="Search tile designs"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <Button
            size="sm"
            onClick={() => {
              setEditing(null);
              setDialogOpen(true);
            }}
          >
            <Plus className="size-4" />
            New design
          </Button>
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

      <TileDesignDialog open={dialogOpen} onOpenChange={setDialogOpen} template={editing} />

      <ConfirmDeleteDialog
        open={!!deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        title="Confirm delete"
        description={
          <>
            Delete <strong>{deleting?.name}</strong>? Any products block using it loses its
            design. This action cannot be undone.
          </>
        }
        successMessage="Tile design deleted"
        queryKeysToInvalidate={[['dealer-kit', 'tile-templates']]}
        onDelete={async () => {
          if (deleting) await deleteTileTemplate(deleting.id);
        }}
      />
    </DataGrid>
  );
}
