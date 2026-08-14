import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import { MODEL_OPTIONS } from '@/app/(protected)/system-management/ai-assistant/lib/modelOptions';

/**
 * Option lists for the chatbot media settings page.
 *
 * The image provider and model lists are NOT redefined here - they come from
 * `system-management/ai-assistant/lib/modelOptions`, which is already shared between
 * the global assistant setting and each agent's own row. A third copy would drift the
 * first time a model was added to one of them.
 */

/**
 * Models offered for the image lanes. With no provider chosen the setting inherits
 * the AI assistant's provider, which we do not know here - so offer every model
 * rather than an empty list the operator cannot get past.
 */
export function imageModelOptions(provider: string): SearchableSelectOption[] {
  const forProvider = MODEL_OPTIONS[provider];
  if (forProvider) return forProvider;
  return Object.entries(MODEL_OPTIONS).flatMap(([key, models]) =>
    models.map((model) => ({ ...model, group: key === 'openai' ? 'OpenAI' : 'Anthropic' })),
  );
}

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
