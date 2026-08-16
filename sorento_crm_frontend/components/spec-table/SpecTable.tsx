'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from '@tanstack/react-table';
import { MoreVertical, Pencil, Plus, TriangleAlert } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { readable, readableValue } from '@/lib/spec-readable';
import { SpecSourceBadge } from './SpecSourceBadge';
import { SpecValueCell, toDraft } from './SpecValueCell';
import type { SpecKeyDefinition, SpecScalar, SpecTableCallbacks, SpecTableRow } from './types';

/**
 * Every specification this product carries, editable in place.
 *
 * **The shared `DataGrid`, like every other table in the system** (D10). The obvious
 * alternative - a CSS grid, because "a table with an editable cell is a different
 * kind of table" - is exactly the parallel implementation the component-library rule
 * exists to stop: it would arrive without column resizing, without saved column
 * preferences, without the empty state, and it would drift from the rest of the system
 * the first time any of those changed.
 *
 * **Props-driven** (AC-A.12): rows, vocabulary and callbacks in; nothing fetched here.
 * The product page and milestone 2's supplier portal both render this, against
 * different APIs and different principals.
 */
export function SpecTable({
  rows,
  registry,
  callbacks,
  isLoading = false,
  canEdit = true,
  openEditorFor = null,
  onEditorOpened,
  listingKey = 'master_data.products.view::product-specifications',
}: {
  rows: SpecTableRow[];
  /** The registry, for the synonym lookup behind "add this word to the key". */
  registry: SpecKeyDefinition[];
  callbacks: SpecTableCallbacks;
  isLoading?: boolean;
  /** False renders the table read-only: no edit affordance, no row menu, no CTA. */
  canEdit?: boolean;
  /**
   * Open this key's editor, adding an empty row for it when the product has none.
   *
   * The add-a-specification picker names a key; it does not set a value, because an
   * empty value is not a value - stored, it would raise the same conflict on every
   * derivation run forever, and the API refuses one for that reason. So the picker
   * hands the key here and the person types the value on the row, in the same place
   * they would edit any other.
   *
   * That row has to be MADE. `rows` is built from the values the product holds, and
   * the picker only ever offers keys it does not hold, so waiting for the row to turn
   * up meant waiting for something nothing was going to write: the dialog closed and
   * the table was unchanged, for a new key and an existing one alike.
   */
  openEditorFor?: string | null;
  /** Called once the editor has been opened, so the caller can clear its request. */
  onEditorOpened?: () => void;
  listingKey?: string;
}) {
  /** Which row is in edit, by key. One at a time: two open editors on one product
      invite a person to change two things and save one. */
  const [editingKey, setEditingKey] = useState<string | null>(null);
  /**
   * The value under edit, held here and not in the cell: the grid remounts a cell when
   * the registry refetches under it, and adding a word to a key's vocabulary causes
   * exactly that refetch. A draft kept in the cell reset to the old value at the very
   * moment it should have become the new word.
   */
  const [editDraft, setEditDraft] = useState('');
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const startEdit = useCallback((row: SpecTableRow) => {
    setEditingKey(row.specKey);
    setEditDraft(toDraft(row.value));
  }, []);
  /** The row whose removal is being confirmed, and which of the two intents it is. */
  const [removing, setRemoving] = useState<{ row: SpecTableRow; intent: 'absent' | 'revert' } | null>(
    null,
  );

  /**
   * A key picked from the dialog that this product does not carry yet.
   *
   * It lives here rather than in the caller because it is not a fact about the
   * product: nothing is written until the value is saved, and cancelling has to leave
   * the table exactly as it was.
   */
  const [draftKey, setDraftKey] = useState<string | null>(null);

  const synonymsByKey = useMemo(
    () => new Map(registry.map((key) => [key.spec_key, key.synonyms ?? {}])),
    [registry],
  );

  const definitionsByKey = useMemo(
    () => new Map(registry.map((key) => [key.spec_key, key])),
    [registry],
  );

  useEffect(() => {
    if (!openEditorFor) return;
    const existing = rows.find((row) => row.specKey === openEditorFor);
    setEditingKey(openEditorFor);
    setEditDraft(existing ? toDraft(existing.value) : '');
    setDraftKey(existing ? null : openEditorFor);
    onEditorOpened?.();
    // `rows` is read, not depended on: the request is answered once, at the moment the
    // picker makes it, and re-running on every refetch would re-open a closed editor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openEditorFor, onEditorOpened]);

  /** The rows plus the picked key, until the save that turns it into a real one. */
  const tableRows = useMemo<SpecTableRow[]>(() => {
    if (!draftKey || rows.some((row) => row.specKey === draftKey)) return rows;
    const definition = definitionsByKey.get(draftKey);
    if (!definition) return rows;
    const draft: SpecTableRow = {
      specKey: definition.spec_key,
      label: definition.label || readable(definition.spec_key),
      value: null,
      unit: definition.unit ?? null,
      dataType: definition.data_type ?? 'text',
      options: definition.allowed_values ?? [],
      source: null,
      evidence: null,
      unknownKey: false,
      conflict: null,
    };
    // Sorted in, not appended: the reader is scanning labels, and a row that arrives
    // at the bottom is a row they have to hunt for after the save moves it.
    return [...rows, draft].sort((a, b) => a.label.localeCompare(b.label));
  }, [rows, draftKey, definitionsByKey]);

  /** The save landed and the server's own row took over. */
  useEffect(() => {
    if (draftKey && rows.some((row) => row.specKey === draftKey)) setDraftKey(null);
  }, [rows, draftKey]);

  const columns = useMemo<ColumnDef<SpecTableRow>[]>(
    () => [
      {
        accessorKey: 'label',
        header: ({ column }) => <DataGridColumnHeader title="Specification" column={column} />,
        size: 200,
        minSize: 130,
        enableSorting: false,
        meta: { headerTitle: 'Specification' },
        cell: ({ row }) => (
          <div className="flex min-w-0 items-center gap-1.5">
            <span className="truncate text-sm font-medium" title={row.original.label}>
              {row.original.label}
            </span>
            {row.original.conflict && (
              // Setting the right value IS the resolution (D9), so the hint says what
              // to do rather than offering an action that would only mark it read.
              <span
                role="img"
                aria-label={`The rules now read ${readableValue(
                  row.original.conflict.proposed,
                  row.original.conflict.proposedUnit ?? undefined,
                )}. Correct the value to settle it.`}
                title={`The rules now read ${readableValue(
                  row.original.conflict.proposed,
                  row.original.conflict.proposedUnit ?? undefined,
                )}. Correct the value to settle it.`}
                data-spec-conflict={row.original.specKey}
                className="shrink-0"
              >
                <TriangleAlert className="size-3.5 text-amber-600" />
              </span>
            )}
          </div>
        ),
      },
      {
        id: 'value',
        header: ({ column }) => <DataGridColumnHeader title="Value" column={column} />,
        size: 300,
        minSize: 180,
        enableSorting: false,
        meta: { headerTitle: 'Value' },
        cell: ({ row }) => (
          <SpecValueCell
            row={row.original}
            editing={canEdit && editingKey === row.original.specKey}
            draft={editingKey === row.original.specKey ? editDraft : ''}
            onDraftChange={setEditDraft}
            busy={busyKey === row.original.specKey}
            synonyms={synonymsByKey.get(row.original.specKey)}
            onStartEdit={() => canEdit && startEdit(row.original)}
            onCancel={() => {
              setEditingKey(null);
              // A cancelled draft leaves nothing behind: it was never a value.
              if (draftKey === row.original.specKey) setDraftKey(null);
            }}
            onAddValueToKey={
              callbacks.onAddValueToKey
                ? (value) => callbacks.onAddValueToKey!(row.original.specKey, value)
                : undefined
            }
            onSave={async (value: SpecScalar) => {
              setBusyKey(row.original.specKey);
              try {
                await callbacks.onSetValue(row.original.specKey, value);
                setEditingKey(null);
              } finally {
                setBusyKey(null);
              }
            }}
          />
        ),
      },
      {
        id: 'source',
        header: ({ column }) => <DataGridColumnHeader title="Source" column={column} />,
        size: 190,
        minSize: 130,
        enableSorting: false,
        meta: { headerTitle: 'Source' },
        cell: ({ row }) => (
          <SpecSourceBadge source={row.original.source} evidence={row.original.evidence} />
        ),
      },
      {
        id: 'actions',
        header: '',
        size: 90,
        enableSorting: false,
        enableResizing: false,
        meta: { headerTitle: 'Actions' },
        cell: ({ row }) => {
          if (!canEdit || row.original.unknownKey) return null;
          return (
            <div className="flex items-center justify-end gap-0.5">
              <Button
                variant="ghost"
                size="icon"
                className="size-8"
                aria-label={`Edit ${row.original.label}`}
                onClick={() => startEdit(row.original)}
              >
                <Pencil className="size-4" />
              </Button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-8"
                    aria-label={`More actions for ${row.original.label}`}
                  >
                    <MoreVertical className="size-4" />
                  </Button>
                </DropdownMenuTrigger>
                {/* Plain action names, captain's call: this page is the product
                    editor, not a review surface. "Remove" takes the row off the
                    table and records the absence so the next catalogue run does not
                    refill it (a removal that comes back is not a removal); "Reset"
                    hands the key back to the rules. The confirmation carries the
                    consequence. */}
                <DropdownMenuContent align="end">
                  <DropdownMenuItem
                    onClick={() => setRemoving({ row: row.original, intent: 'absent' })}
                  >
                    Remove
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() => setRemoving({ row: row.original, intent: 'revert' })}
                  >
                    Reset
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          );
        },
      },
    ],
    [canEdit, editingKey, editDraft, busyKey, callbacks, synonymsByKey, draftKey, startEdit],
  );

  const table = useReactTable({
    columns,
    data: tableRows,
    getRowId: (row) => row.specKey,
    getCoreRowModel: getCoreRowModel(),
    // A product carries a median of 4 spec keys and at most 14. Paging that would be
    // a control the reader has to operate to see a list that already fits.
    manualPagination: true,
    pageCount: 1,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  return (
    <div className="flex flex-col gap-3">
      {canEdit && callbacks.onAddSpecification && (
        <div className="flex justify-end">
          <Button variant="outline" size="sm" onClick={callbacks.onAddSpecification}>
            <Plus className="size-4" />
            Add a specification
          </Button>
        </div>
      )}

      <DataGrid
        table={table}
        recordCount={tableRows.length}
        isLoading={isLoading}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
        listingKey={listingKey}
        emptyMessage={
          <div className="py-10 text-center" data-spec-table-empty>
            <p className="text-sm font-medium text-foreground">
              Nothing has been read from this product yet
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              Add the first specification, or read the product again with the current rules.
            </p>
            {canEdit && callbacks.onAddSpecification && (
              <Button
                variant="outline"
                size="sm"
                className="mt-3"
                onClick={callbacks.onAddSpecification}
              >
                <Plus className="size-4" />
                Add a specification
              </Button>
            )}
          </div>
        }
      >
        <Card>
          <CardTable>
            {/* Horizontal scroll INSIDE the table's own container: at 375px four
                columns cannot fit, and without this the page itself scrolls sideways
                and takes the rest of the product record with it. */}
            <ScrollArea>
              <DataGridTable />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          </CardTable>
        </Card>
      </DataGrid>

      <ConfirmDeleteDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={removing?.intent === 'absent' ? 'Confirm delete' : 'Reset'}
        description={
          removing?.intent === 'absent' ? (
            <>
              <strong>{removing?.row.label}</strong> will be removed from this product and will
              not be filled in again automatically. This action cannot be undone.
            </>
          ) : (
            <>
              <strong>{removing?.row.label}</strong> goes back to whatever the rules read from
              this product. This action cannot be undone.
            </>
          )
        }
        successMessage={
          removing?.intent === 'absent' ? 'Specification removed' : 'Back to what the rules read'
        }
        onDelete={async () => {
          if (!removing) return;
          if (removing.intent === 'absent') await callbacks.onTombstone(removing.row.specKey);
          else await callbacks.onRevert(removing.row.specKey);
        }}
        onSuccess={() => setRemoving(null)}
      />
    </div>
  );
}
