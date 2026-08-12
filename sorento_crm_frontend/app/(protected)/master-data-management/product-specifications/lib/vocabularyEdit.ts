import type { SpecRegistryKey } from '../types/productSpec.types';

/**
 * Working out what a vocabulary edit means, kept apart from the form that collects it.
 *
 * The API replaces `suppressed_synonyms` and `suppressed_values` wholesale, so the
 * editor has to send the WHOLE suppression list every time, not the part it changed in
 * this sitting. Getting that wrong is invisible on screen and silently undoes an
 * earlier removal, so it is worth having somewhere it can be tested on its own.
 */

const dedupe = (list: string[]) => Array.from(new Set(list));

/**
 * The words the SEED ships for a value: the live ones plus the ones already taken
 * away, minus anything staff added.
 *
 * Reading this off `synonyms` alone is the trap. `synonyms` is the merged view with
 * suppression already applied, so a word suppressed last week is simply absent — and an
 * editor that asks "which shipped words are missing from the box?" cannot see it, omits
 * it from the payload, and reinstates it.
 */
export function seedWordsFor(key: SpecRegistryKey, value: string): string[] {
  const live = key.synonyms?.[value] ?? [];
  const gone = key.suppressed_synonyms?.[value] ?? [];
  const mine = key.user_synonyms?.[value] ?? [];
  return dedupe([...live, ...gone]).filter((word) => !mine.includes(word));
}

/** The values the SEED ships: the live ones minus staff's, plus the suppressed ones. */
export function seedValuesFor(key: SpecRegistryKey): string[] {
  const mine = key.user_values ?? [];
  return dedupe([
    ...key.allowed_values.filter((value) => !mine.includes(value)),
    ...(key.suppressed_values ?? []),
  ]);
}

export interface WordEdit {
  /** value -> the words currently in the box */
  words: Record<string, string[]>;
  /** value -> the shipped words currently struck through */
  dropped: Record<string, string[]>;
}

/** What to send for a word edit: staff's own additions, and the full suppression list. */
export function wordPayload(
  key: SpecRegistryKey,
  { words, dropped }: WordEdit,
): { user_synonyms: Record<string, string[]>; suppressed_synonyms: Record<string, string[]> } {
  const added: Record<string, string[]> = {};
  const suppressed: Record<string, string[]> = {};
  for (const value of dedupe([...Object.keys(words), ...Object.keys(dropped)])) {
    const seed = seedWordsFor(key, value);
    const current = words[value] ?? [];
    const mine = current.filter((word) => !seed.includes(word));
    const gone = dedupe(dropped[value] ?? []).filter(
      (word) => seed.includes(word) && !current.includes(word),
    );
    if (mine.length > 0) added[value] = mine;
    if (gone.length > 0) suppressed[value] = gone;
  }
  return { user_synonyms: added, suppressed_synonyms: suppressed };
}

/**
 * What to send for a value edit.
 *
 * `user_values` is filtered against the SEED list, not the merged one. Filtering
 * against merged counted a value staff had already saved as shipped, so adding a second
 * value silently dropped the first.
 */
export function valuePayload(
  key: SpecRegistryKey,
  live: string[],
  dropped: string[],
): { user_values: string[]; suppressed_values: string[] } {
  const seed = seedValuesFor(key);
  return {
    user_values: live.filter((value) => !seed.includes(value)),
    suppressed_values: dropped,
  };
}
