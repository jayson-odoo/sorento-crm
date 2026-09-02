'use client';

import { useCallback, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  seedValuesFor,
  seedWordsFor,
  valuePayload,
  wordPayload,
} from '../lib/vocabularyEdit';
import { useSpecRegistryMutations } from './useSpecRegistryMutations';
import { SPEC_REGISTRY_QUERY_KEY } from './useSpecRegistryQuery';
import type { SpecDerivationRule, SpecRegistryKey } from '../types/productSpec.types';

export const dedupe = (list: string[]) => Array.from(new Set(list));

/**
 * The editable projection of a registry row (B.2).
 *
 * Everything a tab renders an input for lives here, seeded from the row on `edit()`
 * and diffed back into the ONE PATCH body on `save()`. Values and words are held as
 * two lists apiece - the live ones and the shipped ones taken away - rather than one
 * list plus a lock, because removing a value means something different depending on
 * who owns it and a lock cannot express that (ported from the retired
 * `SpecKeyEditor`).
 */
export interface SpecKeyDraft {
  label: string;
  unit: string;
  /** Input string; '' clears the cap (AC-D.3 of the folded plan). */
  maxValue: string;
  /** `allowed_values` currently in force. */
  liveValues: string[];
  /** Shipped values taken away. Survives a save that was not about them. */
  droppedValues: string[];
  /** value -> the words currently shown. */
  words: Record<string, string[]>;
  /** value -> the shipped words currently struck through. */
  droppedWords: Record<string, string[]>;
  /** value -> the display label a person reads instead of the slug (#423). */
  valueLabels: Record<string, string>;
  rules: SpecDerivationRule[];
}

export interface UseSpecKeyRecordResult {
  mode: 'view' | 'edit';
  draft: SpecKeyDraft | null;
  saving: boolean;
  edit: () => void;
  cancel: () => void;
  save: () => Promise<boolean>;
  setDraft: (updater: (draft: SpecKeyDraft) => SpecKeyDraft) => void;
}

/** Every value that could carry customer wording, merged the way the vocabulary is. */
function wordedValuesFor(row: SpecRegistryKey): string[] {
  const isBoolean = row.data_type === 'boolean';
  return dedupe([
    ...(isBoolean ? ['true'] : row.allowed_values),
    ...Object.keys(row.synonyms ?? {}),
    ...Object.keys(row.user_synonyms ?? {}),
    ...Object.keys(row.suppressed_synonyms ?? {}),
  ]);
}

/**
 * A registry row, projected into the editable shape (B.2, B.3).
 *
 * Exported so `ValuesAndWordsTab`/`RulesTab` render VIEW mode off this SAME
 * projection rather than a second, hand-written reading of the row - the "field
 * labels in both modes are identical" snapshot (G.8) holds by construction because
 * both modes walk the one shape, only swapping the control each field renders.
 */
export function projectSpecKeyDraft(row: SpecRegistryKey): SpecKeyDraft {
  const wordedValues = wordedValuesFor(row);
  const words: Record<string, string[]> = Object.fromEntries(
    wordedValues.map((value) => [
      value,
      dedupe([
        ...(row.synonyms?.[value] ?? []),
        ...(row.user_synonyms?.[value] ?? []),
      ]),
    ]),
  );
  const droppedWords: Record<string, string[]> = Object.fromEntries(
    Object.entries(row.suppressed_synonyms ?? {}).map(([value, list]) => [
      value,
      [...list],
    ]),
  );
  return {
    label: row.label,
    unit: row.unit ?? '',
    maxValue:
      row.max_value === null || row.max_value === undefined
        ? ''
        : String(row.max_value),
    liveValues: [...row.allowed_values],
    droppedValues: [...(row.suppressed_values ?? [])],
    words,
    droppedWords,
    valueLabels: { ...(row.value_labels ?? {}) },
    // Given an identity on the way in so dragging (RulesTab) moves a RULE, not a
    // position, and Try it/preview keep reading the same row across an edit.
    rules: (row.effective_rules ?? row.derivation_rules ?? []).map((rule, index) => ({
      ...rule,
      _uid: rule._uid ?? `r${index}`,
    })),
  };
}

/** value_labels trimmed; a blank label drops the key (AC-D.3 of the folded plan). */
function trimmedValueLabels(labels: Record<string, string>): Record<string, string> {
  const next: Record<string, string> = {};
  for (const [value, label] of Object.entries(labels)) {
    const trimmed = label.trim();
    if (trimmed) next[value] = trimmed;
  }
  return next;
}

function buildPatchBody(row: SpecRegistryKey, draft: SpecKeyDraft) {
  const { user_synonyms, suppressed_synonyms } = wordPayload(row, {
    words: draft.words,
    dropped: draft.droppedWords,
  });
  const { user_values, suppressed_values } = valuePayload(
    row,
    draft.liveValues,
    draft.droppedValues,
  );
  const maxValueTrimmed = draft.maxValue.trim();
  const maxValueNumber = maxValueTrimmed === '' ? null : Number(maxValueTrimmed);
  const maxValuePayload =
    maxValueTrimmed === ''
      ? { max_value: null }
      : Number.isFinite(maxValueNumber)
        ? { max_value: maxValueNumber }
        : {};

  return {
    label: draft.label.trim() || row.label,
    unit: draft.unit.trim() ? draft.unit.trim() : null,
    ...maxValuePayload,
    user_synonyms,
    suppressed_synonyms,
    user_values,
    suppressed_values,
    // Rides the PATCH even though the backend does not persist it yet (S4 ships the
    // column). The mock echo happens below, once the PATCH has resolved.
    value_labels: trimmedValueLabels(draft.valueLabels),
    derivation_rules: draft.rules,
  };
}

/**
 * Edit-mode state for one registry row (B.2), and the one PATCH `save()` sends.
 *
 * `useSpecKeyRecord(row)` re-derives its draft from whatever `row` is CURRENT the
 * moment `edit()` is called, so a key selected from a freshly-refetched list always
 * starts an edit session from what is on screen.
 */
export function useSpecKeyRecord(row: SpecRegistryKey | undefined): UseSpecKeyRecordResult {
  const [mode, setMode] = useState<'view' | 'edit'>('view');
  const [draft, setDraftState] = useState<SpecKeyDraft | null>(null);
  const { update } = useSpecRegistryMutations();
  const queryClient = useQueryClient();

  const edit = useCallback(() => {
    if (!row) return;
    setDraftState(projectSpecKeyDraft(row));
    setMode('edit');
  }, [row]);

  const cancel = useCallback(() => {
    setDraftState(null);
    setMode('view');
  }, []);

  const setDraft = useCallback((updater: (current: SpecKeyDraft) => SpecKeyDraft) => {
    setDraftState((current) => (current ? updater(current) : current));
  }, []);

  const save = useCallback(async () => {
    if (!row || !draft) return false;
    try {
      const body = buildPatchBody(row, draft);
      const updated = await update.mutateAsync({ specKey: row.spec_key, body });
      // Phase 1 mock (D9, folded #423): the real response never carries
      // `value_labels` until S4 adds the column, so the save would otherwise look
      // like it did nothing. Merged onto the cache in the SAME write the PATCH
      // response lands in - see `useSpecRegistryMutations.update` for why this
      // hook, not the mutation's own `onSuccess`, owns the cache write.
      const merged: SpecRegistryKey = { ...updated, value_labels: body.value_labels };
      queryClient.setQueryData<{ keys: SpecRegistryKey[] }>(
        SPEC_REGISTRY_QUERY_KEY,
        (old) =>
          old
            ? {
                keys: old.keys.map((key) =>
                  key.spec_key === row.spec_key ? merged : key,
                ),
              }
            : old,
      );
      toast.success(`${merged.label} saved`, {
        description:
          draft.rules.length > 0
            ? 'Read the catalogue again to apply it to products.'
            : undefined,
      });
      setDraftState(null);
      setMode('view');
      return true;
    } catch {
      // useSpecRegistryMutations already toasted the reason; leave the session
      // open so nothing typed is lost and the refused field can be corrected.
      return false;
    }
  }, [row, draft, update, queryClient]);

  return {
    mode,
    draft,
    saving: update.isPending,
    edit,
    cancel,
    save,
    setDraft,
  };
}

// Re-exported so a tab needs one import for both the state hook and the seed
// lookups it hands each row (ported wholesale from `SpecKeyEditor`).
export { seedValuesFor, seedWordsFor };
