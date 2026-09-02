'use client';

import { useState } from 'react';
import { Undo2, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import TokenInput from '../TokenInput';
import { readableValue } from '@/lib/spec-readable';
import {
  dedupe,
  seedValuesFor,
  seedWordsFor,
  type SpecKeyDraft,
} from '../../hooks/useSpecKeyRecord';
import type { SpecRegistryKey } from '../../types/productSpec.types';

/** One labelled control. The label is the only chrome a field needs, present in
 *  both view and edit so a field's identity never moves between the two (B.2). */
function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}

const normaliseValue = (raw: string) =>
  raw.trim().toLowerCase().replace(/\s+/g, '_');

/**
 * One row per merged allowed value (AC-B.3): a display-label field, the slug, the
 * customer words, and suppress/restore. A value the seed ships is suppressible with
 * an Undo; a value staff added (an enum row typed in, or a numeric/open-vocabulary
 * value that only ever exists as a worded row) is removed outright - there is
 * nothing shipped to come back to.
 */
function ValueRow({
  value,
  isBoolean,
  isSeed,
  isSuppressed,
  isUserAdded,
  label,
  words,
  seedWords,
  droppedWords,
  mode,
  onLabelChange,
  onWordsChange,
  onRestoreWord,
  onSuppress,
  onRestore,
  onRemove,
}: {
  value: string;
  isBoolean: boolean;
  isSeed: boolean;
  isSuppressed: boolean;
  isUserAdded: boolean;
  label: string;
  words: string[];
  seedWords: string[];
  droppedWords: string[];
  mode: 'view' | 'edit';
  onLabelChange?: (label: string) => void;
  onWordsChange?: (words: string[]) => void;
  onRestoreWord?: (word: string) => void;
  onSuppress?: () => void;
  onRestore?: () => void;
  onRemove?: () => void;
}) {
  const displayName = value === 'true' && isBoolean ? 'When true' : readableValue(value);

  return (
    <div
      className={`flex flex-col gap-2 rounded-md border bg-background p-3 ${
        isSuppressed ? 'opacity-70' : ''
      }`}
      data-spec-value-row={value}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`truncate text-sm font-medium ${
            isSuppressed ? 'text-muted-foreground line-through decoration-muted-foreground/60' : ''
          }`}
        >
          {displayName}
        </span>
        <code className="truncate text-xs text-muted-foreground">{value}</code>
        {isUserAdded && (
          <Badge variant="primary" appearance="light" size="sm">
            user
          </Badge>
        )}
        <div className="ml-auto flex items-center gap-1">
          {mode === 'edit' && isSeed && !isBoolean && (
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="size-7 text-muted-foreground hover:text-foreground"
              aria-label={isSuppressed ? `Put ${displayName} back` : `Suppress ${displayName}`}
              title={isSuppressed ? 'Put back' : 'Suppress'}
              onClick={isSuppressed ? onRestore : onSuppress}
            >
              {isSuppressed ? <Undo2 className="size-3.5" /> : <X className="size-3.5" />}
            </Button>
          )}
          {mode === 'edit' && !isSeed && isUserAdded && (
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="size-7 text-muted-foreground hover:text-destructive"
              aria-label={`Remove ${displayName}`}
              title="Remove"
              onClick={onRemove}
            >
              <X className="size-3.5" />
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Display label">
          {mode === 'edit' ? (
            <Input
              value={label}
              placeholder={readableValue(value)}
              onChange={(event) => onLabelChange?.(event.target.value)}
              maxLength={60}
              className="h-8"
              aria-label={`Display label for ${displayName}`}
              disabled={isSuppressed}
            />
          ) : (
            <span className="text-sm">{label || readableValue(value)}</span>
          )}
        </Field>
        <Field label="Words customers say">
          {mode === 'edit' ? (
            <TokenInput
              values={words}
              muted={seedWords}
              suppressed={droppedWords}
              onRestore={onRestoreWord}
              onChange={(next) => onWordsChange?.(next)}
              placeholder="add a word"
              ariaLabel={`Words customers say for ${displayName}`}
            />
          ) : words.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {words.map((word) => (
                <Badge key={word} variant="secondary" appearance="light" size="sm">
                  {word}
                </Badge>
              ))}
            </div>
          ) : (
            <span className="text-sm text-muted-foreground">No words yet</span>
          )}
        </Field>
      </div>
    </div>
  );
}

export interface ValuesAndWordsTabProps {
  row: SpecRegistryKey;
  mode: 'view' | 'edit';
  /** Null in view mode - the tab reads straight off `row` then. */
  draft: SpecKeyDraft | null;
  setDraft: (updater: (draft: SpecKeyDraft) => SpecKeyDraft) => void;
  /** The empty state's CTA enters edit mode on this tab (B.3), same as Rules'. */
  onEnterEdit: () => void;
}

export function ValuesAndWordsTab({
  row,
  mode,
  draft,
  setDraft,
  onEnterEdit,
}: ValuesAndWordsTabProps) {
  const [newValue, setNewValue] = useState('');
  const isBoolean = row.data_type === 'boolean';

  // View mode reads the row's own merged columns; edit mode reads the draft. Both
  // walk the SAME shape below, so the field list cannot drift between them (G.8).
  const liveValues = draft ? draft.liveValues : row.allowed_values;
  const droppedValues = draft ? draft.droppedValues : (row.suppressed_values ?? []);
  const words = draft
    ? draft.words
    : Object.fromEntries(
        dedupe([
          ...(isBoolean ? ['true'] : row.allowed_values),
          ...Object.keys(row.synonyms ?? {}),
        ]).map((value) => [value, row.synonyms?.[value] ?? []]),
      );
  const valueLabels = draft ? draft.valueLabels : (row.value_labels ?? {});

  const rowValues = dedupe([
    ...(isBoolean ? ['true'] : liveValues),
    ...droppedValues,
    ...Object.keys(words),
  ]);

  if (rowValues.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-md border border-dashed p-8 text-center">
        <p className="text-sm font-medium">No values yet</p>
        {mode === 'edit' ? (
          <AddValueControl
            value={newValue}
            onChange={setNewValue}
            onAdd={(value) => {
              setDraft((d) => ({
                ...d,
                liveValues: dedupe([...d.liveValues, value]),
                words: { ...d.words, [value]: d.words[value] ?? [] },
              }));
              setNewValue('');
            }}
          />
        ) : (
          <Button type="button" size="sm" variant="outline" onClick={onEnterEdit}>
            Add value
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {rowValues.map((value) => (
        <ValueRow
          key={value}
          value={value}
          isBoolean={isBoolean}
          isSeed={seedValuesFor(row).includes(value)}
          isSuppressed={droppedValues.includes(value)}
          isUserAdded={
            !isBoolean &&
            !seedValuesFor(row).includes(value) &&
            !droppedValues.includes(value)
          }
          label={valueLabels[value] ?? ''}
          words={words[value] ?? []}
          seedWords={seedWordsFor(row, value)}
          droppedWords={draft?.droppedWords[value] ?? []}
          mode={mode}
          onLabelChange={(label) =>
            setDraft((d) => ({
              ...d,
              valueLabels: { ...d.valueLabels, [value]: label },
            }))
          }
          onWordsChange={(next) =>
            setDraft((d) => {
              const current = d.words[value] ?? [];
              const removed = current.find((w) => !next.includes(w));
              if (removed) {
                const seed = seedWordsFor(row, value);
                const nextDropped = seed.includes(removed)
                  ? { ...d.droppedWords, [value]: dedupe([...(d.droppedWords[value] ?? []), removed]) }
                  : d.droppedWords;
                return {
                  ...d,
                  words: { ...d.words, [value]: current.filter((w) => w !== removed) },
                  droppedWords: nextDropped,
                };
              }
              const added = next.find((w) => !current.includes(w));
              if (added && (d.droppedWords[value] ?? []).includes(added)) {
                return {
                  ...d,
                  droppedWords: {
                    ...d.droppedWords,
                    [value]: (d.droppedWords[value] ?? []).filter((w) => w !== added),
                  },
                  words: { ...d.words, [value]: dedupe([...current, added]) },
                };
              }
              return { ...d, words: { ...d.words, [value]: next } };
            })
          }
          onRestoreWord={(word) =>
            setDraft((d) => ({
              ...d,
              droppedWords: {
                ...d.droppedWords,
                [value]: (d.droppedWords[value] ?? []).filter((w) => w !== word),
              },
              words: { ...d.words, [value]: dedupe([...(d.words[value] ?? []), word]) },
            }))
          }
          onSuppress={() =>
            setDraft((d) => ({
              ...d,
              liveValues: d.liveValues.filter((v) => v !== value),
              droppedValues: dedupe([...d.droppedValues, value]),
            }))
          }
          onRestore={() =>
            setDraft((d) => ({
              ...d,
              droppedValues: d.droppedValues.filter((v) => v !== value),
              liveValues: dedupe([...d.liveValues, value]),
            }))
          }
          onRemove={() =>
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
                words: nextWords,
                droppedWords: nextDroppedWords,
                valueLabels: nextValueLabels,
              };
            })
          }
        />
      ))}

      {mode === 'edit' && !isBoolean && (
        <AddValueControl
          value={newValue}
          onChange={setNewValue}
          onAdd={(value) => {
            setDraft((d) => ({
              ...d,
              liveValues: dedupe([...d.liveValues, value]),
              words: { ...d.words, [value]: d.words[value] ?? [] },
            }));
            setNewValue('');
          }}
        />
      )}

      {mode === 'edit' && row.data_type === 'numeric' && (
        <Field label={`Ignore values above${row.unit ? ` (${row.unit})` : ''}`}>
          <Input
            type="number"
            step="1"
            min="0"
            placeholder="no cap"
            className="h-8 w-40"
            value={draft?.maxValue ?? ''}
            onChange={(event) =>
              setDraft((d) => ({ ...d, maxValue: event.target.value }))
            }
          />
        </Field>
      )}
    </div>
  );
}

function AddValueControl({
  value,
  onChange,
  onAdd,
}: {
  value: string;
  onChange: (value: string) => void;
  onAdd: (value: string) => void;
}) {
  const commit = () => {
    const normalised = normaliseValue(value);
    if (!normalised) return;
    onAdd(normalised);
  };
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Input
        className="w-52"
        value={value}
        placeholder="a value, e.g. matte_black"
        aria-label="Add value"
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key !== 'Enter') return;
          event.preventDefault();
          commit();
        }}
      />
      <Button type="button" size="sm" variant="outline" onClick={commit}>
        Add value
      </Button>
    </div>
  );
}

export default ValuesAndWordsTab;
