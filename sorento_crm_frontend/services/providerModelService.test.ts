/**
 * The wire shape of the two model calls.
 *
 * Thin on purpose, but the provider must reach the query string: the media page
 * asks with a blank provider (meaning "inherit the assistant's"), and dropping it
 * would silently answer for the wrong provider - the same class of mix-up that
 * let a Gemini model id be saved against an OpenAI key.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));
vi.mock('@/lib/api-client', () => ({
  extractApiError: async (_r: unknown, fallback: string) => fallback,
}));

import { getProviderModels, testProviderModel } from './providerModelService';

function ok(body: unknown) {
  return { ok: true, json: async () => body };
}

beforeEach(() => apiFetch.mockReset());

describe('getProviderModels', () => {
  it('asks for the named provider and returns the list with its source', async () => {
    apiFetch.mockResolvedValue(
      ok({ provider: 'gemini', source: 'live', message: null, models: [] }),
    );

    const result = await getProviderModels('gemini');

    expect(apiFetch).toHaveBeenCalledWith(
      '/api/v1/system/ai-assistant/models?provider=gemini',
    );
    expect(result.source).toBe('live');
  });

  it('sends a blank provider through rather than dropping the parameter', async () => {
    apiFetch.mockResolvedValue(
      ok({ provider: 'openai', source: 'live', message: null, models: [] }),
    );

    await getProviderModels('');

    expect(apiFetch).toHaveBeenCalledWith('/api/v1/system/ai-assistant/models?provider=');
  });

  it('throws with the extracted message when the call fails', async () => {
    apiFetch.mockResolvedValue({ ok: false, json: async () => ({}) });

    await expect(getProviderModels('openai')).rejects.toThrow(
      'Failed to load the model list',
    );
  });
});

describe('testProviderModel', () => {
  it('posts the provider and model and returns the verdict', async () => {
    apiFetch.mockResolvedValue(ok({ ok: false, message: '404 retired', latency_ms: 12 }));

    const result = await testProviderModel('gemini', 'gemini-2.5-flash-lite');

    expect(apiFetch).toHaveBeenCalledWith('/api/v1/system/ai-assistant/test-model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider: 'gemini',
        model: 'gemini-2.5-flash-lite',
        with_image: false,
      }),
    });
    // A model that does not work is a 200 carrying `ok: false`, not a thrown error:
    // the provider's sentence is the answer the operator needs.
    expect(result).toEqual({ ok: false, message: '404 retired', latency_ms: 12 });
  });

  it('asks for an image probe when the field certifies an image model', async () => {
    apiFetch.mockResolvedValue(ok({ ok: true, message: 'OK', latency_ms: 9 }));

    await testProviderModel('openai', 'gpt-4o', true);

    const body = JSON.parse(apiFetch.mock.calls[0][1].body);
    expect(body.with_image).toBe(true);
  });
});
