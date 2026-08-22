import type { SearchableSelectOption } from '@/components/common/SearchableSelect';

/**
 * Option lists for the chatbot media settings page.
 *
 * The image model list is NOT here any more. It used to be a slice of a hardcoded
 * table, and with no provider chosen it offered every provider's models at once -
 * so a Gemini id could be saved against an OpenAI key, and a model Google had
 * retired stayed on offer indefinitely. The page now asks the provider through
 * `useProviderModels`, which also resolves a blank provider to the assistant's
 * own rather than guessing.
 */

export const LANGUAGE_MODE_OPTIONS: SearchableSelectOption[] = [
  { value: 'pinned', label: 'Pinned to one language' },
  { value: 'hints', label: 'Hint list' },
  { value: 'auto', label: 'Auto-detect' },
];

/**
 * The languages a Sorento dealer actually sends a voice note in. Kept short on
 * purpose: a hint list is a hint, and a long one is the same as no hint at all.
 */
export const LANGUAGE_OPTIONS: SearchableSelectOption[] = [
  { value: 'en', label: 'English' },
  { value: 'ms', label: 'Malay' },
  { value: 'zh', label: 'Chinese' },
  { value: 'ta', label: 'Tamil' },
  { value: 'id', label: 'Indonesian' },
];

/**
 * Transcription models. `whisper-1` is the live behaviour and stays the default until
 * the captain changes it here; the point of the setting is that changing it needs no
 * deploy. A model missing from this list can still be typed in, same as the assistant
 * model pickers.
 */
export const TRANSCRIBE_MODEL_OPTIONS: SearchableSelectOption[] = [
  { value: 'whisper-1', label: 'Whisper v1' },
  { value: 'gpt-4o-transcribe', label: 'GPT-4o transcribe' },
  { value: 'gpt-4o-mini-transcribe', label: 'GPT-4o mini transcribe' },
];

export function parseCsv(raw: string | null | undefined): string[] {
  return (raw ?? '')
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
}

export function toCsv(values: string[]): string {
  return Array.from(new Set(values)).join(',');
}
