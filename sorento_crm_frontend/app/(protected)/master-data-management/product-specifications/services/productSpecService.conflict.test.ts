/**
 * Security review fix round (#1286, S1) - the synchronous re-read on a rule
 * save shares one guard with the catalogue preview: while one runs, the next
 * PATCH is refused with a 409, "Products are still being updated from
 * another change. Try again in a moment." `updateSpecKey` reaches that
 * message through `extractApiError`, the same as every other ordinary
 * failure (see `productSpecService.similarError.test.ts`, which covers the
 * 422 near-duplicate shape this file does not).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api';
import { updateSpecKey } from './productSpecService';

const mockedFetch = vi.mocked(apiFetch);

const BUSY = 'Products are still being updated from another change. Try again in a moment.';

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

beforeEach(() => vi.clearAllMocks());

describe('updateSpecKey - a busy catalogue read answers 409 (S1)', () => {
  it('throws the exact server message, through extractApiError', async () => {
    mockedFetch.mockResolvedValue(jsonResponse({ detail: BUSY }, 409));

    const thrown = await updateSpecKey('finish', {
      derivation_rules: [{ builder: { kind: 'words', words: ['NEW'], value: 'chrome' } }],
    }).catch((e) => e as Error);

    expect(thrown.message).toBe(BUSY);
  });
});
