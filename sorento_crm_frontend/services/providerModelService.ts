import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * The models a provider will take, and whether one of them actually works.
 *
 * Two calls rather than one because the answers are different: a provider's
 * catalogue says what EXISTS, and only a real call says what WORKS. Google lists
 * `gemini-2.5-flash-lite` to a key that gets `404 ... no longer available to new
 * users` on the first generateContent, which is how a model picked from a valid
 * list silently broke every over-quota photo in the chatbot media lane.
 */

export interface ProviderModelOption {
  value: string;
  label: string;
}

export interface ProviderModelsResult {
  provider: string;
  /** "live" = the provider answered. "fallback" = the built-in list, see `message`. */
  source: 'live' | 'fallback';
  message: string | null;
  models: ProviderModelOption[];
}

export interface TestModelResult {
  ok: boolean;
  message: string;
  latency_ms: number;
}

export async function getProviderModels(provider: string): Promise<ProviderModelsResult> {
  const response = await apiFetch(
    `/api/v1/system/ai-assistant/models?provider=${encodeURIComponent(provider)}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the model list'));
  }
  return response.json();
}

/**
 * `withImage` attaches a 1x1 PNG to the probe. The image fields pass it because a
 * text-only model answers the plain probe and then fails on every real photo.
 */
export async function testProviderModel(
  provider: string,
  model: string,
  withImage = false,
): Promise<TestModelResult> {
  const response = await apiFetch('/api/v1/system/ai-assistant/test-model', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider, model, with_image: withImage }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to test the model'));
  }
  return response.json();
}
