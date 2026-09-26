'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowUpDown, MoreHorizontal } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { DeferredCountdown } from '@/components/common/DeferredActionButton';
import { readableValue } from '@/lib/spec-readable';
import { useSpecKeyProductsQuery } from '../../hooks/useSpecKeyProductsQuery';
import { dedupe, type SpecKeyDraft } from '../../hooks/useSpecKeyRecord';
import type { SpecRegistryKey } from '../../types/productSpec.types';

/** `_self` names the specification itself, never a choice (D7); this tab never
 *  renders it - its words live on Details as "Other names for this specification". */
const SELF_KEY = '_self';

const REMOVE_WINDOW_SECONDS = 5;
type SortColumn = 'choice' | 'products';

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

/**
 * Choices and words (AC-S1.15): a data grid, one row per choice - Choice, Words
 * customers say, Products - each header sortable. Clicking a Choice or Words cell
 * edits it in place (words as a comma list); Add a choice adds a row; Remove is a
 * deferred 5s action. No chips, no cards, no `_self` row, no "user" badge, no code
 * name (D13; owner ruling 27 Sep 2026, "this should be tabulated with data grid").
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

  const [sort, setSort] = useState<{ column: SortColumn; desc: boolean }>({
    column: 'products',
    desc: true,
  });
  const [editing, setEditing] = useState<{ value: string; column: 'choice' | 'words' } | null>(null);
  const [adding, setAdding] = useState(false);
  const [newChoice, setNewChoice] = useState('');
  const [removals, setRemovals] = useState<
    Record<string, { commitAt: number; timer: ReturnType<typeof setTimeout> }>
  >({});
  const draftRef = useRef(draft);
  draftRef.current = draft;

  useEffect(() => {
    return () => {
      Object.values(removals).forEach((r) => clearTimeout(r.timer));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  const sorted = [...choices].sort((a, b) => {
    if (sort.column === 'products') {
      const diff = (countByValue.get(a) ?? 0) - (countByValue.get(b) ?? 0);
      return sort.desc ? -diff : diff;
    }
    const labelA = readableValue(a, undefined, valueLabels);
    const labelB = readableValue(b, undefined, valueLabels);
    const diff = labelA.localeCompare(labelB);
    return sort.desc ? -diff : diff;
  });

  const toggleSort = (column: SortColumn) =>
    setSort((current) => ({ column, desc: current.column === column ? !current.desc : false }));

  const startRemoval = (value: string) => {
    const commitAt = Date.now() + REMOVE_WINDOW_SECONDS * 1000;
    const timer = setTimeout(() => {
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
      setRemovals((current) => {
        const next = { ...current };
        delete next[value];
        return next;
      });
    }, REMOVE_WINDOW_SECONDS * 1000);
    setRemovals((current) => ({ ...current, [value]: { commitAt, timer } }));
  };

  const cancelRemoval = (value: string) => {
    setRemovals((current) => {
      const removal = current[value];
      if (removal) clearTimeout(removal.timer);
      const next = { ...current };
      delete next[value];
      return next;
    });
  };

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
    <div className="overflow-hidden rounded-md border">
      <table className="w-full table-fixed text-sm">
        <colgroup>
          <col className="w-[24%]" />
          <col className="w-[46%]" />
          <col className="w-[20%]" />
          <col className="w-[10%]" />
        </colgroup>
        <thead>
          <tr className="border-b bg-muted/40">
            <th className="p-2 text-left font-medium">
              <button
                type="button"
                className="inline-flex items-center gap-1 hover:underline"
                onClick={() => toggleSort('choice')}
              >
                Choice <ArrowUpDown className="size-3" aria-hidden />
              </button>
            </th>
            <th className="p-2 text-left font-medium">Words customers say</th>
            <th className="p-2 text-left font-medium">
              <button
                type="button"
                className="inline-flex items-center gap-1 hover:underline"
                onClick={() => toggleSort('products')}
              >
                Products <ArrowUpDown className="size-3" aria-hidden />
              </button>
            </th>
            <th className="p-2" />
          </tr>
        </thead>
        <tbody>
          {sorted.map((value) => {
            const removal = removals[value];
            const displayName =
              value === 'true' && isBoolean ? 'Yes' : readableValue(value, undefined, valueLabels);
            const wordList = words[value] ?? [];
            const productCount = countByValue.get(value) ?? 0;

            if (removal) {
              return (
                <tr key={value} className="border-b last:border-0">
                  <td className="p-2" colSpan={4}>
                    <DeferredCountdown
                      pending={{
                        id: value,
                        action_key: 'spec_choice.remove',
                        entity_type: 'spec_choice',
                        entity_id: value,
                        commit_at: new Date(removal.commitAt).toISOString(),
                        window_seconds: REMOVE_WINDOW_SECONDS,
                      }}
                      verb="Removing"
                      subject={displayName}
                      onCancel={() => cancelRemoval(value)}
                    />
                  </td>
                </tr>
              );
            }

            const editingChoice = editing?.value === value && editing.column === 'choice';
            const editingWords = editing?.value === value && editing.column === 'words';
            const canEdit = mode === 'edit' && !isBoolean;

            return (
              <tr key={value} className="border-b last:border-0">
                <td className="truncate p-2 font-medium" title={displayName}>
                  {canEdit && editingChoice ? (
                    <Input
                      autoFocus
                      defaultValue={displayName}
                      className="h-8"
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
                  ) : (
                    <button
                      type="button"
                      disabled={!canEdit}
                      onClick={() => canEdit && setEditing({ value, column: 'choice' })}
                      className={canEdit ? 'hover:underline' : ''}
                    >
                      {displayName}
                    </button>
                  )}
                </td>
                <td className="truncate p-2" title={wordList.join(', ')}>
                  {mode === 'edit' && editingWords ? (
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
                  ) : (
                    <button
                      type="button"
                      disabled={mode !== 'edit'}
                      onClick={() => mode === 'edit' && setEditing({ value, column: 'words' })}
                      className={mode === 'edit' ? 'text-left hover:underline' : 'text-left'}
                    >
                      {wordList.length > 0 ? (
                        wordList.join(', ')
                      ) : (
                        <span className="text-muted-foreground">No words yet</span>
                      )}
                    </button>
                  )}
                </td>
                <td className="p-2 tabular-nums">{productCount.toLocaleString()}</td>
                <td className="p-2 text-right">
                  {canEdit && (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          aria-label={`${displayName} actions`}
                          className="size-7 text-muted-foreground"
                        >
                          <MoreHorizontal className="size-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => setEditing({ value, column: 'choice' })}>
                          Edit
                        </DropdownMenuItem>
                        <DropdownMenuItem variant="destructive" onClick={() => startRemoval(value)}>
                          Remove
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                </td>
              </tr>
            );
          })}
          {mode === 'edit' && !isBoolean && (
            <tr>
              <td colSpan={4} className="p-2">
                {adding ? (
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
                    className="text-primary hover:underline"
                    onClick={() => setAdding(true)}
                  >
                    + Add a choice
                  </button>
                )}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export default ValuesAndWordsTab;
