/** LOOKUP-EMBED-CENTRAL slice 5: the route-local service goes through apiFetch to the right endpoints. */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { overview, lookupWords, tryResult } from './embeddingsStubs';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

import {
  embedMissing,
  getLookupWords,
  getOverview,
  recordsBackfill,
  tryPhrase,
} from '../services/embeddingsService';

const ok = (body: unknown, status = 200) => ({ ok: true, status, json: async () => body });

beforeEach(() => apiFetch.mockReset());

describe('embeddingsService', () => {
  it('getOverview reads /system/embeddings/overview', async () => {
    apiFetch.mockResolvedValue(ok(overview));
    expect(await getOverview()).toEqual(overview);
    expect(apiFetch.mock.calls[0][0]).toBe('/api/v1/system/embeddings/overview');
  });

  it('getLookupWords reads the chatbot doorway with the list', async () => {
    apiFetch.mockResolvedValue(ok(lookupWords));
    await getLookupWords('file_type');
    expect(apiFetch.mock.calls[0][0]).toBe('/api/v1/system/chatbot/lookup-words?list=file_type');
  });

  it('tryPhrase posts {phrase}', async () => {
    apiFetch.mockResolvedValue(ok(tryResult));
    await tryPhrase('toilet bowl');
    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/v1/system/chatbot/lookup-words/try');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ phrase: 'toilet bowl' });
  });

  it('embedMissing posts to embed-missing', async () => {
    apiFetch.mockResolvedValue(ok({ job_id: 'j' }, 202));
    await embedMissing();
    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/v1/system/chatbot/lookup-words/embed-missing');
    expect(init.method).toBe('POST');
  });

  it('recordsBackfill posts the action', async () => {
    apiFetch.mockResolvedValue(ok({}, 202));
    await recordsBackfill('stop');
    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/v1/system/embeddings/records-backfill');
    expect(JSON.parse(init.body)).toEqual({ action: 'stop' });
  });

  it('turns a failed response into an Error carrying the server message', async () => {
    apiFetch.mockResolvedValue({ ok: false, status: 403, json: async () => ({ detail: 'Not allowed' }), text: async () => 'Not allowed' });
    await expect(getOverview()).rejects.toThrow(/not allowed/i);
  });
});
