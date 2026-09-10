'use client';

import { useMemo, useState } from 'react';
import { ColumnDef, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { Pencil, Plus, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardHeading, CardTable, CardToolbar } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Skeleton } from '@/components/ui/skeleton';

import { useDeferredRowAction, useRowPending } from '@/hooks/useDeferredRowAction';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

import { TEXT_GLOSSARY_LIST_KEY, useTextGlossary } from '../hooks/useTextGlossary';
import type { TextGlossaryEntry } from '../types/textGlossary.types';
import { TextGlossaryFormDialog } from './TextGlossaryFormDialog';

/** One frozen empty array while the query is in flight: TanStack reads `data` by
 *  identity, and a fresh `[]` per render is a render loop with a clean console
 *  (`data-grid.stable-data.inventory.test.ts`). */
const NO_ROWS: TextGlossaryEntry[] = [];

/**
 * System Management > Text Glossary (S2, AC-E4): every word an operator has typed the
 * English for, beside Import Column Mappings and Translations. No `locale` column (R9 -
 * every row here is `en` until a second target language exists) and no pagination - a
 * glossary an operator builds one word at a time never grows large enough to need one
 * (matching the backend contract, `text-glossary-acceptance-criteria.md` E4).
 */
export default function TextGlossaryList() {
  const {
    value: searchQuery,
    setValue: setSearchQuery,
    debouncedValue: debouncedSearch,
    isSettling: debouncedSearchSettling,
  } = useDebouncedSearch();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<TextGlossaryEntry | null>(null);

  const { data, isLoading, isFetching, isError, error } = useTextGlossary(debouncedSearch);
  // Delete asks nothing (D7): the row dims and a toast counts down with Cancel.
  const deletion = useDeferredRowAction({
    actionKey: 'text_glossary.forget',
    entityType: 'text_glossary',
    verb: 'Removing',
    successMessage: 'Glossary entry removed',
    invalidateKeys: [TEXT_GLOSSARY_LIST_KEY],
  });
  const rowPending = useRowPending<TextGlossaryEntry>('text_glossary');

  const rows = data ?? NO_ROWS;

  const columns = useMemo<ColumnDef<TextGlossaryEntry>[]>(
    () => [
      {
        accessorKey: 'source_text',
        header: ({ column }) => <DataGridColumnHeader title="Source text" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.source_text}>
            {row.original.source_text}
          </span>
        ),
        size: 260,
        meta: { headerTitle: 'Source text', skeleton: <Skeleton className="h-5 w-40" /> },
      },
      {
        accessorKey: 'translation',
        header: ({ column }) => <DataGridColumnHeader title="Translation" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.translation}>
            {row.original.translation}
          </span>
        ),
        size: 260,
        meta: { headerTitle: 'Translation' },
      },
      {
        accessorKey: 'created_by_name',
        header: ({ column }) => <DataGridColumnHeader title="Added by" column={column} />,
        cell: ({ row }) => (
          <span className="truncate text-muted-foreground" title={row.original.created_by_name ?? undefined}>
            {row.original.created_by_name || '-'}
          </span>
        ),
        enableSorting: false,
        size: 160,
        meta: { headerTitle: 'Added by' },
      },
      {
        accessorKey: 'created_at',
        header: ({ column }) => <DataGridColumnHeader title="Added" column={column} />,
        cell: ({ row }) => (
          <span className="text-muted-foreground">
            {formatDateTimeInMalaysia(row.original.created_at)}
          </span>
        ),
        size: 170,
        meta: { headerTitle: 'Added' },
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
              aria-label={`Edit ${row.original.source_text}`}
              title="Edit translation"
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
              aria-label={`Delete ${row.original.source_text}`}
              title="Delete entry"
              onClick={() =>
                deletion.run({ id: row.original.id, subject: row.original.source_text })
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
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const addButton = (
    <Button
      onClick={() => {
        setEditing(null);
        setFormOpen(true);
      }}
    >
      <Plus className="size-4" />
      Add entry
    </Button>
  );

  return (
    <div className="space-y-3">
      {isError ? (
        <div
          className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
          data-testid="text-glossary-error"
        >
          {error instanceof Error ? error.message : 'Failed to load the glossary.'}
        </div>
      ) : null}

      <DataGrid
        table={table}
        recordCount={rows.length}
        isLoading={isLoading}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        rowPending={rowPending}
        emptyAction={addButton}
        emptyMessage="No words learnt yet. Add one, or type the English straight onto a proforma invoice row."
      >
        <Card>
          <CardHeader className="flex items-center justify-between gap-3">
            <CardHeading>
              <ListSearchInput
                value={searchQuery}
                onChange={setSearchQuery}
                isSettling={isSearchInFlight(debouncedSearchSettling, isFetching, debouncedSearch)}
                placeholder="Search the glossary..."
                aria-label="Search the glossary"
                className="w-64"
              />
            </CardHeading>
            <CardToolbar>{addButton}</CardToolbar>
          </CardHeader>

          <CardTable>
            <DataGridTable />
          </CardTable>
        </Card>
      </DataGrid>

      <TextGlossaryFormDialog
        open={formOpen}
        onOpenChange={(next) => {
          setFormOpen(next);
          if (!next) setEditing(null);
        }}
        entry={editing}
      />
    </div>
  );
}
