'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  ColumnDef,
  PaginationState,
  SortingState,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Pencil, Plus, Trash2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardFooter,
  CardHeader,
  CardHeading,
  CardTable,
  CardToolbar,
} from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Skeleton } from '@/components/ui/skeleton';

import {
  useCreateMessageSnippet,
  useMessageSnippets,
  useUpdateMessageSnippet,
} from '../hooks/useMessageSnippets';
import {
  useDeferredRowAction,
  useRowPending,
} from '@/hooks/useDeferredRowAction';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import type {
  MessageSnippet,
  MessageSnippetFormData,
} from '../types/messageSnippet.types';
import MessageSnippetFormDialog from './MessageSnippetFormDialog';

export default function MessageSnippetsList() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 10 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const {
    value: searchQuery,
    setValue: setSearchQuery,
    debouncedValue: debouncedSearch,
    isSettling: debouncedSearchSettling,
  } = useDebouncedSearch();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<MessageSnippet | null>(null);

  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [debouncedSearch, sorting]);

  const { data, isLoading, isError, error } = useMessageSnippets({
    pageIndex: pagination.pageIndex,
    pageSize: pagination.pageSize,
    sorting,
    searchQuery: debouncedSearch,
  });
  const createSnippet = useCreateMessageSnippet();
  const updateSnippet = useUpdateMessageSnippet();
  // Delete asks nothing (D7): the row dims and a toast counts down with Cancel.
  const deletion = useDeferredRowAction({
    actionKey: 'message_snippet.delete',
    entityType: 'message_snippet',
    successMessage: 'Snippet deleted',
    invalidateKeys: [['message-snippets'], ['message-snippet-options']],
  });
  const rowPending = useRowPending<MessageSnippet>('message_snippet');

  const rows = useMemo<MessageSnippet[]>(() => data?.data ?? [], [data]);
  const total = data?.pagination?.total ?? 0;

  const columns = useMemo<ColumnDef<MessageSnippet>[]>(
    () => [
      {
        accessorKey: 'name',
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        cell: ({ row }) => (
          <span className="truncate font-medium" title={row.original.name}>
            {row.original.name}
          </span>
        ),
        size: 200,
        meta: { headerTitle: 'Name', skeleton: <Skeleton className="h-5 w-32" /> },
      },
      {
        accessorKey: 'shortcut',
        header: ({ column }) => <DataGridColumnHeader title="Shortcut" column={column} />,
        cell: ({ row }) =>
          row.original.shortcut ? (
            <span className="truncate font-mono text-xs" title={`/${row.original.shortcut}`}>
              /{row.original.shortcut}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 130,
        meta: { headerTitle: 'Shortcut' },
      },
      {
        accessorKey: 'body',
        header: ({ column }) => <DataGridColumnHeader title="Message" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate text-muted-foreground" title={row.original.body}>
            {row.original.body}
          </span>
        ),
        enableSorting: false,
        size: 380,
        meta: { headerTitle: 'Message' },
      },
      {
        accessorKey: 'is_active',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) =>
          row.original.is_active ? (
            <Badge variant="success" appearance="light" size="md">
              Active
            </Badge>
          ) : (
            <Badge variant="secondary" appearance="light" size="md">
              Inactive
            </Badge>
          ),
        size: 110,
        meta: { headerTitle: 'Status' },
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              aria-label={`Edit ${row.original.name}`}
              title="Edit snippet"
              onClick={() => {
                setEditing(row.original);
                setFormOpen(true);
              }}
            >
              <Pencil className="size-4" />
            </Button>
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              aria-label={`Delete ${row.original.name}`}
              title="Delete snippet"
              onClick={() =>
                deletion.run({ id: row.original.id, subject: row.original.name })
              }
            >
              <Trash2 className="size-4 text-destructive" />
            </Button>
          </div>
        ),
        size: 100,
        enableSorting: false,
        meta: { headerTitle: 'Actions', cellClassName: 'text-right' },
      },
    ],
    [deletion],
  );

  const table = useReactTable({
    columns,
    data: rows,
    pageCount: Math.max(1, Math.ceil(total / pagination.pageSize)),
    rowCount: total,
    getRowId: (row) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const submit = async (form: MessageSnippetFormData) => {
    if (editing) {
      await updateSnippet.mutateAsync({ id: editing.id, body: form });
    } else {
      await createSnippet.mutateAsync(form);
    }
    setFormOpen(false);
    setEditing(null);
  };

  return (
    <div className="space-y-3">
      {isError ? (
        <div
          className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
          data-testid="snippets-error"
        >
          {error instanceof Error ? error.message : 'Failed to load message snippets.'}
        </div>
      ) : null}

      <DataGrid
        table={table}
        recordCount={total}
        isLoading={isLoading}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        rowPending={rowPending}
        emptyMessage="No snippets yet. Add one and it appears in the ticket composer."
      >
        <Card>
          <CardHeader className="flex items-center justify-between gap-3">
            <CardHeading>
              <ListSearchInput
                value={searchQuery}
                onChange={setSearchQuery}
                isSettling={debouncedSearchSettling}
                placeholder="Search snippets..."
                aria-label="Search snippets"
                className="w-64"
              />
            </CardHeading>
            <CardToolbar>
              <Button
                onClick={() => {
                  setEditing(null);
                  setFormOpen(true);
                }}
              >
                <Plus className="size-4" />
                Add snippet
              </Button>
            </CardToolbar>
          </CardHeader>

          <CardTable>
            <DataGridTable />
          </CardTable>
          <CardFooter>
            <DataGridPagination />
          </CardFooter>
        </Card>
      </DataGrid>

      <MessageSnippetFormDialog
        open={formOpen}
        onOpenChange={(next) => {
          setFormOpen(next);
          if (!next) setEditing(null);
        }}
        snippet={editing}
        onSubmit={submit}
        isSubmitting={createSnippet.isPending || updateSnippet.isPending}
      />

    </div>
  );
}
