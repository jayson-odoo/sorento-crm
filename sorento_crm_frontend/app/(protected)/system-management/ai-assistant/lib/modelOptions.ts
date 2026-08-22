/**
 * The FALLBACK models an agent can be pointed at.
 *
 * Not the source any more: every picker asks the provider itself through
 * `useProviderModels`, because a hand-maintained list goes stale silently. Google
 * retired `gemini-2.5-flash-lite` while it still sat in this table, and the media
 * lane's degraded tier - the one nobody exercises until a contact runs out of
 * allowance - failed every call on it.
 *
 * This list is what a picker shows while the provider cannot be reached (no key
 * configured yet, network down). The backend keeps its own copy for the same
 * reason and serves it with `source: "fallback"`; this one covers the case where
 * the request itself failed. Every screen also accepts a typed-in name.
 *
 * Newest first. The 4o family is kept because existing configuration points at it, not
 * because it is the one to pick.
 */
export const MODEL_OPTIONS: Record<string, { value: string; label: string }[]> = {
  openai: [
    { value: 'gpt-5.4-mini', label: 'GPT-5.4 mini' },
    { value: 'gpt-5.4', label: 'GPT-5.4' },
    { value: 'gpt-4.1', label: 'GPT-4.1' },
    { value: 'gpt-4o-mini', label: 'GPT-4o mini' },
    { value: 'gpt-4o', label: 'GPT-4o' },
  ],
  anthropic: [
    { value: 'claude-haiku-4-5', label: 'Claude Haiku 4.5' },
    { value: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6' },
    { value: 'claude-opus-4-7', label: 'Claude Opus 4.7' },
  ],
  gemini: [
    { value: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro' },
    { value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
    { value: 'gemini-2.5-flash-lite', label: 'Gemini 2.5 Flash Lite' },
  ],
};

export const PROVIDER_OPTIONS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'gemini', label: 'Google Gemini' },
];

/** The provider's display name, for grouping a mixed model list. */
export function providerLabel(provider: string): string {
  return PROVIDER_OPTIONS.find((opt) => opt.value === provider)?.label ?? provider;
}
