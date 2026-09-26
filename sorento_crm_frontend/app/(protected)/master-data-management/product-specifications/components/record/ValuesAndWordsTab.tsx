'use client';

import { useMemo, useState } from 'react';
import { ColumnDef, getCoreRowModel, getSortedRowModel, useReactTable } from '@tanstack/react-table';
import { MoreHorizontal } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { readableValue } from '@/lib/spec-readable';
import { useSpecKeyProductsQuery } from '../../hooks/useSpecKeyProductsQuery';
import { SPEC_REGISTRY_QUERY_KEY } from '../../hooks/useSpecRegistryQuery';
import { dedupe, type SpecKeyDraft } from '../../hooks/useSpecKeyRecord';
import type { SpecRegistryKey } from '../../types/productSpec.types';

/** `_self` names the specification itself, never a choice (D7); this tab never
 *  renders it - its words live on Details as "Other names for this specification". */
const SELF_KEY = '_self';

const normaliseValue = (raw: string) => raw.trim().toLowerCase().replace(/\s+/g, '_');

export interface ValuesAndWordsTabProps {
  row: SpecRegistryKey;
  mode: 'view' | 'edit';
  /** Null in view mode - the tab reads straight off `row` then. */
  draft: SpecKeyDraft | null;
  setDraft: (updater: (draft: SpecKeyDraft) => SpecKeyDraft) => void;
  /** The empty state's CTA enters edit mode on this tab (B.3). */
  onEnterEdit: () => void;
}

interface ChoiceRow {
  value: string;
}

/**
 * Choices and words (AC-S1.15): the shared `DataGrid` (fixed, resizable columns),
 * one row per choice - Choice, Words customers say, Products - each header
 * sortable. Clicking a Choice or Words cell edits it in place (words as a comma
 * list); Add a choice adds a row. No chips, no cards, no `_self` row, no "user"
 * badge, no code name (D13; owner ruling 27 Sep 2026, "this should be tabulated
 * with data grid").
 *
 * Remove is `spec_value.remove` (D7, D8, fix round 1): a server-deferred action,
 * not a local timer - the record is the SPEC KEY (one pending removal per key
 * across every choice), same as the rules grid and the Other-names grid.
 */
export function ValuesAndWordsTab({
  row,
  mode,
  draft,
  setDraft,
  onEnterEdit,
}: ValuesAndWordsTabProps) {
  const isBoolean = row.data_type === 'boolean';
  const isNumeric = row.data_type === 'numeric';
  const canEdit = mode === 'edit' && !isBoolean;

  const [editing, setEditing] = useState<{ value: string; column: 'choice' | 'words' } | null>(null);
  const [adding, setAdding] = useState(false);
  const [newChoice, setNewChoice] = useState('');
  const [removingValue, setRemovingValue] = useState<string | null>(null);

  // The counts a choice's "Products" column shows - the same aggregate the
  // Products tab already fetches, asked for zero rows: this tab needs the
  // by-value counts, not the product list itself.
  const { data: productCounts } = useSpecKeyProductsQuery(row.spec_key, { limit: 1, offset: 0 });
  const countByValue = useMemo(() => {
    const map = new Map<string, number>();
    for (const entry of productCounts?.by_value ?? []) {
      if (entry.value !== null) map.set(entry.value, entry.count);
    }
    return map;
  }, [productCounts]);

  const removal = useDeferredAction({
    actionKey: 'spec_value.remove',
    entityType: 'spec_value',
    entityId: row.spec_key || null,
    verb: 'Removing',
    subject: '',
    surface: 'inline',
    watchFromMount: mode === 'edit',
    successMessage: 'Choice removed',
    invalidateKeys: [SPEC_REGISTRY_QUERY_KEY],
    // The server already dropped it - this only keeps the OPEN draft in step, the
    // same reason `WordsDataGrid` strips a removed word from its own draft.
    onCommitted: () => {
      const value = removingValue;
      if (value) {
        setDraft((d) => {
          const nextWords = { ...d.words };
          delete nextWords[value];
          const nextDroppedWords = { ...d.droppedWords };
          delete nextDroppedWords[value];
          const nextValueLabels = { ...d.valueLabels };
          delete nextValueLabels[value];
          return {
            ...d,
            liveValues: d.liveValues.filter((v) => v !== value),
            droppedValues: d.droppedValues.filter((v) => v !== value),
            words: nextWords,
            droppedWords: nextDroppedWords,
            valueLabels: nextValueLabels,
          };
        });
      }
      setRemovingValue(null);
    },
  });

  const startRemoval = (value: string) => {
    setRemovingValue(value);
    removal.start({ value });
  };

  // View mode reads the row's own merged columns; edit mode reads the draft. Both
  // walk the SAME shape, so the field list cannot drift between them (G.8).
  const liveValues = draft ? draft.liveValues : row.allowed_values;
  const droppedValues = draft ? draft.droppedValues : row.suppressed_values ?? [];
  const words = draft
    ? draft.words
    : Object.fromEntries(
        dedupe([...(isBoolean ? ['true'] : row.allowed_values), ...Object.keys(row.synonyms ?? {})]).map(
          (value) => [value, row.synonyms?.[value] ?? []],
        ),
      );
  const valueLabels = draft ? draft.valueLabels : row.value_labels ?? {};

  const choices = dedupe([
    ...(isBoolean ? ['true'] : liveValues),
    ...droppedValues,
    ...Object.keys(words),
  ]).filter((value) => value !== SELF_KEY);

  const displayName = (value: string) =>
    value === 'true' && isBoolean ? 'Yes' : readableValue(value, undefined, valueLabels);

  const commitAdd = () => {
    const trimmed = newChoice.trim();
    if (!trimmed) {
      setAdding(false);
      return;
    }
    const value = normaliseValue(trimmed);
    setDraft((d) => ({
      ...d,
      liveValues: dedupe([...d.liveValues, value]),
      words: { ...d.words, [value]: d.words[value] ?? [] },
      // Set explicitly, never falling back to a title-cased slug: a choice reads by
      // exactly the words the person typed (no snake_case, D15).
      valueLabels: { ...d.valueLabels, [value]: trimmed },
    }));
    setNewChoice('');
    setAdding(false);
  };

  const rows = useMemo<ChoiceRow[]>(() => choices.map((value) => ({ value })), [choices]);

  const columns = useMemo<ColumnDef<ChoiceRow>[]>(() => {
    const choiceColumn: ColumnDef<ChoiceRow> = {
      id: 'choice',
      accessorFn: (r) => displayName(r.value),
      header: ({ column }) => <DataGridColumnHeader title="Choice" column={column} />,
      cell: ({ row: r }) => {
        const value = r.original.value;
        const name = displayName(value);
        const editingChoice = editing?.value === value && editing.column === 'choice';
        if (canEdit && editingChoice) {
          return (
            <Input
              autoFocus
              defaultValue={name}
              className="h-8"
              aria-label={`Edit ${name}`}
              onBlur={(e) => {
                const next = e.target.value.trim();
                if (next) setDraft((d) => ({ ...d, valueLabels: { ...d.valueLabels, [value]: next } }));
                setEditing(null);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') e.currentTarget.blur();
                if (e.key === 'Escape') setEditing(null);
              }}
            />
          );
        }
        return (
          <button
            type="button"
            disabled={!canEdit}
            onClick={() => canEdit && setEditing({ value, column: 'choice' })}
            className={`block w-full truncate text-left font-medium ${canEdit ? 'hover:underline' : ''}`}
            title={name}
          >
            {name}
          </button>
        );
      },
      size: 170,
      minSize: 120,
    };

    const wordsColumn: ColumnDef<ChoiceRow> = {
      id: 'words',
      enableSorting: false,
      header: ({ column }) => <DataGridColumnHeader title="Words customers say" column={column} />,
      cell: ({ row: r }) => {
        const value = r.original.value;
        const wordList = words[value] ?? [];
        const editingWords = editing?.value === value && editing.column === 'words';
        if (mode === 'edit' && editingWords) {
          return (
            <Input
              autoFocus
              defaultValue={wordList.join(', ')}
              className="h-8"
              onBlur={(e) => {
                const next = dedupe(
                  e.target.value
                    .split(',')
                    .map((w) => w.trim())
                    .filter(Boolean),
                );
                setDraft((d) => ({ ...d, words: { ...d.words, [value]: next } }));
                setEditing(null);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') e.currentTarget.blur();
                if (e.key === 'Escape') setEditing(null);
              }}
            />
          );
        }
        return (
          <button
            type="button"
            disabled={mode !== 'edit'}
            onClick={() => mode === 'edit' && setEditing({ value, column: 'words' })}
            className={`block w-full truncate text-left ${mode === 'edit' ? 'hover:underline' : ''}`}
            title={wordList.join(', ')}
          >
            {wordList.length > 0 ? wordList.join(', ') : <span className="text-muted-foreground">No words yet</span>}
          </button>
        );
      },
      size: 220,
      minSize: 140,
    };

    const productsColumn: ColumnDef<ChoiceRow> = {
      id: 'products',
      accessorFn: (r) => countByValue.get(r.value) ?? 0,
      header: ({ column }) => <DataGridColumnHeader title="Products" column={column} />,
      cell: ({ row: r }) => (
        <span className="tabular-nums">{(countByValue.get(r.original.value) ?? 0).toLocaleString()}</span>
      ),
      size: 100,
      minSize: 80,
    };

    if (!canEdit) return [choiceColumn, wordsColumn, productsColumn];

    const actionsColumn: ColumnDef<ChoiceRow> = {
      id: 'actions',
      header: () => <span className="sr-only">Actions</span>,
      enableSorting: false,
      enableResizing: false,
      cell: ({ row: r }) => {
        const value = r.original.value;
        const name = displayName(value);
        if (removingValue === value) return removal.countdown;
        return (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                aria-label={`${name} actions`}
                className="size-7 text-muted-foreground"
                disabled={removal.isBlocked}
              >
                <MoreHorizontal className="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => setEditing({ value, column: 'choice' })}>Edit</DropdownMenuItem>
              <DropdownMenuItem variant="destructive" onClick={() => startRemoval(value)}>
                Remove
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        );
      },
      size: 60,
      minSize: 60,
    };

    return [choiceColumn, wordsColumn, productsColumn, actionsColumn];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canEdit, mode, editing, removingValue, removal.countdown, removal.isBlocked, words, valueLabels, countByValue]);

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (r) => r.value,
    // Products, descending, by default - the same choice a person cares most
    // about first; the header's own click still flips it.
    initialState: { sorting: [{ id: 'products', desc: true }] },
    enableSortingRemoval: false,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    columnResizeMode: 'onChange',
  });

  if (choices.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-md border border-dashed p-8 text-center">
        {isNumeric ? (
          <p className="text-sm font-medium">
            Numbers have no choices. Other names for this specification are on Details.
          </p>
        ) : (
          <>
            <p className="text-sm font-medium">No choices yet</p>
            {mode === 'edit' ? (
              <div className="flex items-center gap-2">
                <Input
                  className="w-52"
                  value={newChoice}
                  placeholder="a choice, e.g. Rose gold"
                  aria-label="Add a choice"
                  onChange={(e) => setNewChoice(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && commitAdd()}
                />
                <Button type="button" size="sm" variant="outline" onClick={commitAdd}>
                  Add a choice
                </Button>
              </div>
            ) : (
              <Button type="button" size="sm" variant="outline" onClick={onEnterEdit}>
                Add a choice
              </Button>
            )}
          </>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-hidden rounded-md border">
        <DataGrid
          table={table}
          recordCount={rows.length}
          isLoading={false}
          listingKey={null}
          tableLayout={{ width: 'fixed', columnsResizable: true }}
        >
          <DataGridTable />
        </DataGrid>
      </div>

      {mode === 'edit' &&
        !isBoolean &&
        (adding ? (
          <Input
            autoFocus
            value={newChoice}
            placeholder="a choice, e.g. Rose gold"
            className="h-8"
            onChange={(e) => setNewChoice(e.target.value)}
            onBlur={commitAdd}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitAdd();
              if (e.key === 'Escape') {
                setNewChoice('');
                setAdding(false);
              }
            }}
          />
        ) : (
          <button
            type="button"
            className="self-start text-sm text-primary hover:underline"
            onClick={() => setAdding(true)}
          >
            + Add a choice
          </button>
        ))}
    </div>
  );
}

export default ValuesAndWordsTab;
