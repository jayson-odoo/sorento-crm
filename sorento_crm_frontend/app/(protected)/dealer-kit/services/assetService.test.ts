/**
 * The Dealer Kit asset library service, against the real routes.
 *
 * `renameAsset` is the FE half of PLAN-brand-font-manage.md: this file pins
 * the request shape the route expects and that a non-2xx surfaces through
 * `extractApiError`, never a hand-rolled parse. Delete has no service
 * function of its own to test here - it goes through the deferred
 * `/pending-actions` route (`pendingActionService`), and the backend's own
 * `DELETE /assets/{id}` stays only as the immediate route the record action
 * executes.
 */
import { afterEach, describe, expect, it, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { fontAssetUrl, renameAsset } from './assetService';

function ok(body: unknown) {
  return { ok: true, json: async () => body } as unknown as Response;
}

function fail(message: string, status = 409) {
  return {
    ok: false,
    status,
    headers: { get: () => 'application/json' },
    json: async () => ({ message, code: 'CONFLICT', detail: null }),
    text: async () => JSON.stringify({ message }),
  } as unknown as Response;
}

beforeEach(() => {
  apiFetch.mockReset();
});

describe('renameAsset', () => {
  it('PATCHes the id with the new name', async () => {
    apiFetch.mockResolvedValue(
      ok({ id: 'a-1', name: 'Sorento Display', kind: 'font', tags: [], url: null, mime_type: null }),
    );

    const result = await renameAsset('a-1', 'Sorento Display');

    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/v1/dealer-kit/assets/a-1');
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(init.body)).toEqual({ name: 'Sorento Display' });
    expect(result.name).toBe('Sorento Display');
  });

  it('surfaces the extracted message on a 409', async () => {
    apiFetch.mockResolvedValue(fail('"Sorento Display" is already the name of another brand font.'));

    await expect(renameAsset('a-1', 'Sorento Display')).rejects.toThrow(
      '"Sorento Display" is already the name of another brand font.',
    );
  });
});

/**
 * The URL a brand font's bytes are fetched from (price-tag-r4 S1, review 1).
 *
 * It has to be RELATIVE. `NEXT_PUBLIC_*` is inlined into the browser bundle
 * at build time, so `http://localhost:8000` in it means the machine running
 * the browser, not the machine running the backend - `lib/api.ts` documents
 * why `apiFetch` strips it for every browser call for exactly that reason.
 * The editor loads fonts from the page's own origin, and Next's rewrite (dev)
 * or nginx (production) proxies `/api/v1` to the backend.
 */
describe('fontAssetUrl', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('is a bare same-origin path', () => {
    expect(fontAssetUrl('a1b2')).toBe('/api/v1/public/dealer-kit/fonts/a1b2');
  });

  it('stays relative even when NEXT_PUBLIC_API_URL points somewhere else', () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'http://localhost:8000');
    expect(fontAssetUrl('a1b2')).toBe('/api/v1/public/dealer-kit/fonts/a1b2');
  });
});
