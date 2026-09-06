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

import { afterEach, describe, expect, it, vi } from 'vitest';

import { fontAssetUrl } from './assetService';

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('fontAssetUrl', () => {
  it('is a bare same-origin path', () => {
    expect(fontAssetUrl('a1b2')).toBe('/api/v1/public/dealer-kit/fonts/a1b2');
  });

  it('stays relative even when NEXT_PUBLIC_API_URL points somewhere else', () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'http://localhost:8000');
    expect(fontAssetUrl('a1b2')).toBe('/api/v1/public/dealer-kit/fonts/a1b2');
  });
});
