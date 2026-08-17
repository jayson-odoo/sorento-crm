/**
 * The models an agent can be pointed at.
 *
 * Shared because the choice is now made in two places — the global assistant setting
 * and each agent's own row — and two copies of this list would drift the first time a
 * model was added to one of them. Both screens also accept a typed-in name, so a model
 * missing here is an inconvenience, never a blocker.
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
