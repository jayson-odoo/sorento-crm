'use client';

import { useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ColumnDef, getCoreRowModel, getSortedRowModel, useReactTable } from '@tanstack/react-table';
import { ChevronLeft, ChevronRight, MoreHorizontal, Plus, X } from 'lucide-react';
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
import { useHasPermission, usePermissions } from '@/hooks/usePermissions';
import { Skeleton } from '@/components/ui/skeleton';
import { AssetPickerDialog } from '@/app/(protected)/dealer-kit/tag-templates/components/AssetPickerDialog';
import { ICON_LIBRARY_QUERY_KEY, useIconLibraryQuery } from '../../hooks/useIconLibraryQuery';
import { readableValue } from '@/lib/spec-readable';
import { useSpecKeyProductsQuery } from '../../hooks/useSpecKeyProductsQuery';
import { SPEC_REGISTRY_QUERY_KEY } from '../../hooks/useSpecRegistryQuery';
import { dedupe, seedValuesFor, seedWordsFor, type SpecKeyDraft, type WordError } from '../../hooks/useSpecKeyRecord';
import type { SpecRegistryKey } from '../../types/productSpec.types';

/** `_self` names the specification itself, never a choice (D7); this tab never
 *  renders it - its words live on Details as "Other names for this specification". */
const SELF_KEY = '_self';

const normaliseValue = (raw: string) => raw.trim().toLowerCase().replace(/\s+/g, '_');

// Fix round 3 (D1, CRITICAL): a `?? []`/`?? {}` FALLBACK is a fresh literal on every
// render it fires on - reused here instead, so a row whose `suppressed_values`/
// `value_labels` happens to be absent does not hand `choices` (and the `useMemo`
// below it) a new array identity every render. `useReactTable`'s own row models
// (`getSortedRowModel` here) call `table._autoResetPageIndex()` on every recompute
// their memo notices, which THIS grid never turns off - an unstable `data` array
// recomputes it every render, which resets the (unused) pagination state via a
// fresh object every time, which React never bails out of re-rendering for, which
// rebuilds the unstable array again: a render loop with nothing thrown and nothing
// logged (`data-grid.stable-data.inventory.test.ts`'s own finding, M5 run 2).
const EMPTY_STRING_ARRAY: string[] = [];
const EMPTY_LABELS: Record<string, string> = {};
const EMPTY_ICONS: Record<string, string[]> = {};
const NO_ICON_IDS: string[] = [];

export interface ValuesAndWordsTabProps {
  row: SpecRegistryKey;
  mode: 'view' | 'edit';
  /** Null in view mode - the tab reads straight off `row` then. */
  draft: SpecKeyDraft | null;
  setDraft: (updater: (draft: SpecKeyDraft) => SpecKeyDraft) => void;
  /** The empty state's CTA enters edit mode on this tab (B.3). */
  onEnterEdit: () => void;
  /** A refused word, shown under the row it was added to. */
  wordError?: WordError | null;
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
  wordError,
}: ValuesAndWordsTabProps) {
  const isBoolean = row.data_type === 'boolean';
  const isNumeric = row.data_type === 'numeric';
  const canEdit = mode === 'edit' && !isBoolean;

  const [editing, setEditing] = useState<{ value: string; column: 'choice' | 'words' } | null>(null);
  const [adding, setAdding] = useState(false);
  // A Cancel ends the edit session; the next one starts without an open box.
  useEffect(() => {
    if (mode === 'view') setAdding(false);
  }, [mode]);
  const [newChoice, setNewChoice] = useState('');
  const [removingValue, setRemovingValue] = useState<string | null>(null);

  // Feature icons (owner ruling 5 Nov 20:35): each choice carries its own ordered Dealer Kit
  // icons. Changing them needs the Dealer Kit library (`dealer_kit.library.manage`, the gate on
  // the asset list and the picker); without it the names still read, from the registry row.
  const canManageIcons = useHasPermission('dealer_kit.library.manage');
  const { isLoading: permissionsLoading } = usePermissions();
  const { data: iconLibrary, isLoading: iconLibraryLoading } = useIconLibraryQuery(canManageIcons);
  // Until both are known the cell cannot tell "no icons" from "not loaded yet" (crew pass).
  const iconsLoading = permissionsLoading || (canManageIcons && iconLibraryLoading);
  const [iconPickerFor, setIconPickerFor] = useState<string | null>(null);
  const queryClient = useQueryClient();
  // An icon uploaded inside the picker is not in the list the cell names icons from until it
  // is read again (review S2).
  const refreshIconLibrary = () => {
    void queryClient.invalidateQueries({ queryKey: ICON_LIBRARY_QUERY_KEY });
  };
  const iconAssets = useMemo(() => {
    const map = new Map<string, { name: string; thumb: string | null }>();
    for (const [id, name] of Object.entries(row.value_icon_names ?? {})) map.set(id, { name, thumb: null });
    for (const asset of iconLibrary ?? []) {
      map.set(asset.id, { name: asset.name, thumb: asset.thumb_url ?? asset.url ?? null });
    }
    return map;
  }, [row.value_icon_names, iconLibrary]);

  // The counts a choice's "Products" column shows - the same aggregate the
  // Products tab already fetches, asked for zero rows: this tab needs the
  // by-value counts, not the product list itself.
  const { data: productCounts, isPlaceholderData } = useSpecKeyProductsQuery(row.spec_key, {
    limit: 1,
    offset: 0,
  });
  const countByValue = useMemo(() => {
    const map = new Map<string, number>();
    for (const entry of productCounts?.by_value ?? []) {
      if (entry.value !== null) map.set(entry.value, entry.count);
    }
    return map;
  }, [productCounts]);

  /** Take a choice out of the open draft. A built-in one is taken away (B-6): it
   *  goes into `droppedValues`, so the next Save still sends it as suppressed
   *  rather than bringing it back; a staff-added one simply goes. */
  const dropChoice = (value: string) =>
    setDraft((d) => {
      const nextWords = { ...d.words };
      delete nextWords[value];
      const nextDroppedWords = { ...d.droppedWords };
      delete nextDroppedWords[value];
      const nextValueLabels = { ...d.valueLabels };
      delete nextValueLabels[value];
      const nextValueIcons = { ...d.valueIcons };
      delete nextValueIcons[value];
      const builtIn = seedValuesFor(row).includes(value);
      return {
        ...d,
        liveValues: d.liveValues.filter((v) => v !== value),
        droppedValues: builtIn
          ? dedupe([...d.droppedValues, value])
          : d.droppedValues.filter((v) => v !== value),
        words: nextWords,
        droppedWords: nextDroppedWords,
        valueLabels: nextValueLabels,
        valueIcons: nextValueIcons,
      };
    });

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
      if (removingValue) dropChoice(removingValue);
      setRemovingValue(null);
    },
  });

  // B-5: one removal at a time - see `SpecRulesGrid`'s own note.
  const removalBusy = removal.isPending || removal.isBlocked;
  /** Only a choice the server holds has anything for `spec_value.remove` to do. */
  const isSavedChoice = (value: string) => row.allowed_values.includes(value);

  const startRemoval = (value: string) => {
    if (!isSavedChoice(value)) {
      dropChoice(value);
      return;
    }
    if (removalBusy) return;
    setRemovingValue(value);
    removal.start({ value });
  };

  // View mode reads the row's own merged columns; edit mode reads the draft. Both
  // walk the SAME shape, so the field list cannot drift between them (G.8).
  const liveValues = draft ? draft.liveValues : row.allowed_values;
  const droppedValues = draft ? draft.droppedValues : row.suppressed_values ?? EMPTY_STRING_ARRAY;
  const valueLabels = draft ? draft.valueLabels : row.value_labels ?? EMPTY_LABELS;
  const valueIcons = draft ? draft.valueIcons : row.value_icons ?? EMPTY_ICONS;
  const editIcons = mode === 'edit' && canManageIcons;

  /** Rewrite one choice's icon list in the open draft (reassigned, never mutated). */
  const setIcons = (value: string, next: (ids: string[]) => string[]) =>
    setDraft((d) => ({ ...d, valueIcons: { ...d.valueIcons, [value]: next(d.valueIcons[value] ?? []) } }));
  const moveIcon = (value: string, index: number, delta: number) =>
    setIcons(value, (ids) => {
      const out = [...ids];
      const target = index + delta;
      if (target < 0 || target >= out.length) return ids;
      [out[index], out[target]] = [out[target], out[index]];
      return out;
    });

  // Genuinely COMPUTED (not just a property read), so it needs its own memo - the
  // fallback constants above only fix the property-read branches.
  const words = useMemo(
    () =>
      draft
        ? draft.words
        : Object.fromEntries(
            dedupe([...(isBoolean ? ['true'] : row.allowed_values), ...Object.keys(row.synonyms ?? {})]).map(
              (value) => [value, row.synonyms?.[value] ?? EMPTY_STRING_ARRAY],
            ),
          ),
    [draft, isBoolean, row.allowed_values, row.synonyms],
  );

  // A choice the business has taken away is not a choice (B-6): it is neither
  // listed nor counted, whether the removal came from this grid or an earlier Save.
  const choices = useMemo(
    () =>
      dedupe([...(isBoolean ? ['true'] : liveValues), ...Object.keys(words)]).filter(
        (value) => value !== SELF_KEY && !droppedValues.includes(value),
      ),
    [isBoolean, liveValues, droppedValues, words],
  );

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
                // S-5: a built-in word taken out of the list (deleted, or renamed to
                // something else) is taken away, or the next Save brings it back.
                const seed = seedWordsFor(row, value);
                setDraft((d) => {
                  const removed = (d.words[value] ?? []).filter((w) => !next.includes(w) && seed.includes(w));
                  const dropped = dedupe([...(d.droppedWords[value] ?? []), ...removed]).filter(
                    (w) => !next.includes(w),
                  );
                  return {
                    ...d,
                    words: { ...d.words, [value]: next },
                    droppedWords: { ...d.droppedWords, [value]: dropped },
                  };
                });
                setEditing(null);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') e.currentTarget.blur();
                if (e.key === 'Escape') setEditing(null);
              }}
            />
          );
        }
        const others = Array.from(
          new Set(wordList.flatMap((word) => row.also_on?.[word] ?? [])),
        );
        return (
          <div className="min-w-0">
            <button
              type="button"
              disabled={mode !== 'edit'}
              onClick={() => mode === 'edit' && setEditing({ value, column: 'words' })}
              className={`block w-full truncate text-left ${mode === 'edit' ? 'hover:underline' : ''}`}
              title={wordList.join(', ')}
            >
              {wordList.length > 0 ? wordList.join(', ') : <span className="text-muted-foreground">No words yet</span>}
            </button>
            {others.length > 0 && (
              <span className="block truncate text-xs text-muted-foreground">
                Also on: {others.join(', ')}
              </span>
            )}
            {mode === 'edit' &&
              wordError &&
              (wordError.value === value || (wordError.value === null && wordError.word === value)) && (
                <span role="alert" className="block text-xs text-destructive">
                  {wordError.message}
                </span>
              )}
          </div>
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

    const iconsColumn: ColumnDef<ChoiceRow> = {
      id: 'icons',
      enableSorting: false,
      header: ({ column }) => <DataGridColumnHeader title="Icons" column={column} />,
      cell: ({ row: r }) => {
        const value = r.original.value;
        const label = displayName(value);
        const ids = valueIcons[value] ?? NO_ICON_IDS;
        if (iconsLoading) {
          return (
            <div data-testid={`value-icons-${value}`}>
              <Skeleton data-testid="value-icons-loading" className="h-6 w-16" />
            </div>
          );
        }
        return (
          <div data-testid={`value-icons-${value}`} className="flex min-w-0 flex-wrap items-center gap-1">
            {ids.map((id, index) => {
              const asset = iconAssets.get(id);
              const name = asset?.name ?? 'Icon no longer in the library';
              return (
                <span key={id} className="inline-flex min-w-0 items-center gap-0.5 rounded border px-0.5">
                  <span title={name} className="inline-flex min-w-0 items-center">
                    {asset?.thumb ? (
                      <img src={asset.thumb} alt="" className="size-6 object-contain" />
                    ) : (
                      <span className="max-w-24 truncate text-xs">{name}</span>
                    )}
                  </span>
                  {editIcons && index > 0 && (
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="size-7"
                      aria-label={`Move ${name} earlier`}
                      onClick={() => moveIcon(value, index, -1)}
                    >
                      <ChevronLeft className="size-3.5" />
                    </Button>
                  )}
                  {editIcons && index < ids.length - 1 && (
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="size-7"
                      aria-label={`Move ${name} later`}
                      onClick={() => moveIcon(value, index, 1)}
                    >
                      <ChevronRight className="size-3.5" />
                    </Button>
                  )}
                  {editIcons && (
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="size-7"
                      aria-label={`Remove ${name}`}
                      onClick={() => setIcons(value, (list) => list.filter((other) => other !== id))}
                    >
                      <X className="size-3.5" />
                    </Button>
                  )}
                </span>
              );
            })}
            {ids.length === 0 && !editIcons && <span className="text-muted-foreground">No icons</span>}
            {editIcons && (
              <Button
                type="button"
                size="icon"
                variant="outline"
                className="size-6"
                aria-label={`Choose icons for ${label}`}
                onClick={() => setIconPickerFor(value)}
              >
                <Plus className="size-3.5" />
              </Button>
            )}
          </div>
        );
      },
      size: 200,
      minSize: 120,
    };

    if (!canEdit) return [choiceColumn, wordsColumn, iconsColumn, productsColumn];

    const actionsColumn: ColumnDef<ChoiceRow> = {
      id: 'actions',
      header: () => <span className="sr-only">Actions</span>,
      enableSorting: false,
      enableResizing: false,
      cell: ({ row: r }) => {
        const value = r.original.value;
        const name = displayName(value);
        if (removingValue === value && removal.pending) return removal.countdown;
        const saved = isSavedChoice(value);
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
              <DropdownMenuItem
                variant="destructive"
                disabled={saved && removalBusy}
                onClick={() => startRemoval(value)}
              >
                Remove
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        );
      },
      size: 60,
      minSize: 60,
    };

    return [choiceColumn, wordsColumn, iconsColumn, productsColumn, actionsColumn];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    canEdit,
    mode,
    editing,
    removingValue,
    removal.countdown,
    removal.pending,
    removal.isBlocked,
    removalBusy,
    words,
    valueLabels,
    countByValue,
    valueIcons,
    iconAssets,
    editIcons,
    iconsLoading,
    row.allowed_values,
    row.also_on,
    wordError,
  ]);

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
        {/* Add a choice sits at the top right, on the toolbar row above the column
            header, in read mode and edit mode - the same place as Add a rule (fix
            round 5, owner ruling 27 Sep 2026). A yes-or-no specification has its
            one choice already, so it has no toolbar. */}
        {!isBoolean && (
          <div
            data-testid="choices-grid-toolbar"
            className="flex flex-wrap items-center justify-end gap-2 border-b p-2"
          >
            {mode === 'edit' && adding ? (
              <Input
                autoFocus
                value={newChoice}
                placeholder="a choice, e.g. Rose gold"
                aria-label="New choice"
                className="h-8 w-full sm:w-64"
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
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => {
                  // From read mode this opens the edit session first; `adding`
                  // survives the switch, so the box is ready once it renders.
                  if (mode === 'view') onEnterEdit();
                  setAdding(true);
                }}
              >
                <Plus className="size-4" aria-hidden />
                Add a choice
              </Button>
            )}
          </div>
        )}
        <DataGrid
          table={table}
          recordCount={rows.length}
          isLoading={false}
          isPlaceholderData={isPlaceholderData}
          listingKey={null}
          tableLayout={{ width: 'fixed', columnsResizable: true }}
        >
          <DataGridTable />
        </DataGrid>
      </div>
      {/* The Dealer Kit icon library: upload or pick. Each pick appends to the choice's icons
          and the picker stays open, so hot and cold go in one go; Done closes it. */}
      <AssetPickerDialog
        open={iconPickerFor !== null}
        productImages={[]}
        allowProductPhotos={false}
        libraryKind="icon"
        closeLabel="Done"
        title={iconPickerFor ? `Icons for ${displayName(iconPickerFor)}` : 'Icons'}
        onCancel={() => {
          setIconPickerFor(null);
          refreshIconLibrary();
        }}
        onPick={(source) => {
          if (iconPickerFor && source.type === 'asset') {
            const assetId = source.assetId;
            setIcons(iconPickerFor, (ids) => (ids.includes(assetId) ? ids : [...ids, assetId]));
            refreshIconLibrary();
          }
        }}
      />
    </div>
  );
}

export default ValuesAndWordsTab;
