/**
 * The cover-sources payload fails CLOSED on a missing scope (review finding 3, round 2).
 *
 * `cover_scope` reaching the client as `undefined` means one of three things: an older run's
 * payload, a backend that could not resolve the policy, or a field lost on the way. All three
 * are "we do not know", and the policy default for "we do not know" is `own_pool` - the
 * captain's answer ("either I use stock from BRW, or buy"). Defaulting to `all_locations`
 * offered the whole network on exactly the occasions we were least sure we were allowed to.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api';
import { getCoverSources } from './reorderRunService';

const mockedFetch = vi.mocked(apiFetch);

function okResponse(body: unknown): Response {
  return { ok: true, json: async () => body } as Response;
}

const sources = {
  p1: [
    {
      warehouse_id: 'wh-B',
      warehouse_code: 'B',
      segment: 'project',
      qty: 5,
      pool_warehouse_id: 'wh-A',
    },
  ],
};

beforeEach(() => vi.clearAllMocks());

describe('getCoverSources - the scope defaults to own_pool', () => {
  it('reads a payload with no cover_scope as own_pool', async () => {
    mockedFetch.mockResolvedValue(okResponse({ sources }));

    expect(await getCoverSources('run-1')).toEqual({ sources, cover_scope: 'own_pool' });
  });

  it('keeps an explicit all_locations, which is the only way to open the network', async () => {
    mockedFetch.mockResolvedValue(okResponse({ sources, cover_scope: 'all_locations' }));

    expect((await getCoverSources('run-1')).cover_scope).toBe('all_locations');
  });

  it('reads an empty payload as no sources and the closed scope', async () => {
    mockedFetch.mockResolvedValue(okResponse({}));

    expect(await getCoverSources('run-1')).toEqual({ sources: {}, cover_scope: 'own_pool' });
  });
});
