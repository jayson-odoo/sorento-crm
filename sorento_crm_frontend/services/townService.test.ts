import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * SORENTO-TOWN Phase 1: the town snapshot transport (plan "Phase 1 screen", layering).
 * `getSnapshot(etag?, mode?)` sends If-None-Match, answers `{ notModified: true }` on a 304,
 * and takes every other failure through extractApiError.
 *
 * Assumed shape (the plan names only `getSnapshot()`): `getSnapshot(etag?: string, mode?: 'wallboard')`
 * resolves `{ notModified: true }` or `{ notModified: false, snapshot, etag }` where `etag` is the
 * response's ETag header, to be sent back next time.
 */
const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));
const extractApiError = vi.fn();
vi.mock('@/lib/api-client', () => ({
  extractApiError: (...a: unknown[]) => extractApiError(...a),
}));

import { getSnapshot } from './townService';

const BODY = { schema: 1, today: { invoice_count: 321 } };

function response(status: number, body?: unknown, etag?: string) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(etag ? { ETag: etag } : {}),
    json: async () => body,
  } as unknown as Response;
}

function sentHeader(call: unknown[], name: string): string | null {
  const init = (call[1] ?? {}) as RequestInit;
  return new Headers(init.headers).get(name);
}

beforeEach(() => {
  apiFetch.mockReset();
  extractApiError.mockReset().mockResolvedValue('Town is unavailable');
});

describe('townService.getSnapshot', () => {
  it('calls /api/v1/town/snapshot and returns the snapshot with its ETag', async () => {
    apiFetch.mockResolvedValue(response(200, BODY, '"abc-full"'));
    const result = await getSnapshot();
    expect(apiFetch).toHaveBeenCalledTimes(1);
    expect(String(apiFetch.mock.calls[0][0])).toBe('/api/v1/town/snapshot');
    expect(result).toMatchObject({ snapshot: BODY, etag: '"abc-full"' });
    expect((result as { notModified?: boolean }).notModified).toBeFalsy();
  });

  it('adds mode=wallboard when asked', async () => {
    apiFetch.mockResolvedValue(response(200, BODY, '"abc-full-wb"'));
    await getSnapshot(undefined, 'wallboard');
    expect(String(apiFetch.mock.calls[0][0])).toBe('/api/v1/town/snapshot?mode=wallboard');
  });

  it('sends If-None-Match when it has an etag and none when it has not', async () => {
    apiFetch.mockResolvedValue(response(200, BODY, '"v2-full"'));
    await getSnapshot('"v1-full"');
    expect(sentHeader(apiFetch.mock.calls[0], 'if-none-match')).toBe('"v1-full"');
    await getSnapshot();
    expect(sentHeader(apiFetch.mock.calls[1], 'if-none-match')).toBeNull();
  });

  it('answers { notModified: true } on a 304 without reading a body or raising', async () => {
    const res = response(304);
    const json = vi.fn();
    (res as unknown as { json: unknown }).json = json;
    apiFetch.mockResolvedValue(res);
    await expect(getSnapshot('"v1-full"')).resolves.toEqual({ notModified: true });
    expect(json).not.toHaveBeenCalled();
    expect(extractApiError).not.toHaveBeenCalled();
  });

  it('returns a pending snapshot as it is', async () => {
    apiFetch.mockResolvedValue(response(200, { pending: true }));
    const result = await getSnapshot();
    expect((result as { snapshot: unknown }).snapshot).toEqual({ pending: true });
  });

  it('turns an error status into extractApiError(response, fallback), not a hand-rolled parse', async () => {
    const res = response(500);
    apiFetch.mockResolvedValue(res);
    await expect(getSnapshot()).rejects.toThrow('Town is unavailable');
    expect(extractApiError).toHaveBeenCalledTimes(1);
    expect(extractApiError.mock.calls[0][0]).toBe(res);
    expect(typeof extractApiError.mock.calls[0][1]).toBe('string');
  });

  it('surfaces a 429 as an error too (the server refuses polling faster than 30 a minute)', async () => {
    apiFetch.mockResolvedValue(response(429));
    await expect(getSnapshot()).rejects.toThrow();
  });
});
