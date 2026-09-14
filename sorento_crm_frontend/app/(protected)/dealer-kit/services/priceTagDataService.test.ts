/**
 * The CRM's door to the product-data gate and the version history
 * (r9 S5/D18-D19, AC-S5-4 / AC-S5-6 service half).
 *
 * Phase 1 answered every function from the in-memory store in
 * `lib/dealer-kit/product-data-changes.ts` so the screens could be walked
 * before the columns existed. Phase 2 swaps each body for the real call and no
 * caller changes, so what is asserted here is the wire: path, method, body.
 *
 * `updateAllLinePins` matters more than it looks. "Update all" is one press by
 * a person who has read one dialog, so it has to reach EVERY changed line - a
 * loop that stops at the first failure leaves half the sheet on old data with
 * no sign that it did.
 *
 * RED before the coder starts: none of these five functions touches `apiFetch`.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import {
  listLineDataChanges,
  listRequestVersions,
  resolveLinePin,
  restoreRequestVersion,
  updateAllLinePins,
} from './priceTagDataService';

const mockFetch = vi.mocked(apiFetch);

const BASE = '/api/v1/dealer-kit/price-tag-requests';

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as never;
}

function fail(status: number, message: string) {
  return { ok: false, status, json: async () => ({ message }) } as never;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('listLineDataChanges (AC-S5-3)', () => {
  it('reads the resolver output the page already asks the server for', async () => {
    mockFetch.mockResolvedValue(
      ok([
        {
          line_id: 'line-1',
          code: 'ZZT-SINK-1',
          name: 'ZZT Kitchen Sink',
          changes: [
            { field: 'list_price', label: 'List price', old: 'RM 1,000', new: 'RM 1,200' },
          ],
        },
      ]),
    );

    const sets = await listLineDataChanges('req-1');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(String(mockFetch.mock.calls[0][0])).toContain(`${BASE}/req-1`);
    expect(sets).toHaveLength(1);
    expect(sets[0].changes[0].field).toBe('list_price');
  });

  it('a terminal request carries no changes and that is not an error', async () => {
    mockFetch.mockResolvedValue(ok([]));

    await expect(listLineDataChanges('req-1')).resolves.toEqual([]);
  });
});

describe('resolveLinePin (AC-S5-5)', () => {
  it.each(['update', 'keep'] as const)('posts the %s decision for that line', async (action) => {
    mockFetch.mockResolvedValue(ok({ line_id: 'line-1', pinned_at: '2026-09-14T00:00:00Z' }));

    await resolveLinePin('req-1', 'line-1', action);

    expect(mockFetch.mock.calls[0][0]).toBe(`${BASE}/req-1/lines/line-1/pin`);
    const init = mockFetch.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({ action });
  });

  it('raises the server message so the dialog can stay open', async () => {
    mockFetch.mockResolvedValue(fail(409, 'This request is finished'));

    await expect(resolveLinePin('req-1', 'line-1', 'update')).rejects.toThrow(
      'This request is finished',
    );
  });
});

describe('updateAllLinePins (AC-S5-4)', () => {
  it('reaches every changed line', async () => {
    mockFetch.mockResolvedValue(ok({}));

    await updateAllLinePins('req-1', ['line-1', 'line-2', 'line-3']);

    expect(mockFetch.mock.calls.map((call) => call[0])).toEqual([
      `${BASE}/req-1/lines/line-1/pin`,
      `${BASE}/req-1/lines/line-2/pin`,
      `${BASE}/req-1/lines/line-3/pin`,
    ]);
    for (const call of mockFetch.mock.calls) {
      expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({
        action: 'update',
      });
    }
  });

  it('surfaces a failure rather than reporting a partial run as done', async () => {
    mockFetch
      .mockResolvedValueOnce(ok({}))
      .mockResolvedValueOnce(fail(500, 'Could not update the tag'));

    await expect(updateAllLinePins('req-1', ['line-1', 'line-2'])).rejects.toThrow(
      'Could not update the tag',
    );
  });
});

describe('listRequestVersions (AC-S5-6)', () => {
  it('reads the versions route', async () => {
    mockFetch.mockResolvedValue(
      ok([
        {
          version: 2,
          commit_message: 'Marked proof ready',
          created_by_name: 'Mei',
          created_at: '2026-09-14T00:00:00Z',
        },
      ]),
    );

    const rows = await listRequestVersions('req-1');

    expect(mockFetch.mock.calls[0][0]).toBe(`${BASE}/req-1/versions`);
    expect(rows[0].version).toBe(2);
  });
});

describe('restoreRequestVersion (AC-S5-6)', () => {
  it('posts the restore and answers with the NEW version it wrote', async () => {
    mockFetch.mockResolvedValue(
      ok({
        version: 4,
        commit_message: 'Restored v1',
        created_by_name: 'Mei',
        created_at: '2026-09-14T03:00:00Z',
      }),
    );

    const created = await restoreRequestVersion('req-1', 1);

    expect(mockFetch.mock.calls[0][0]).toBe(`${BASE}/req-1/versions/1/restore`);
    expect((mockFetch.mock.calls[0][1] as RequestInit).method).toBe('POST');
    expect(created.version).toBe(4);
    expect(created.commit_message).toBe('Restored v1');
  });

  it('raises when the version has gone', async () => {
    mockFetch.mockResolvedValue(fail(404, 'That version no longer exists'));

    await expect(restoreRequestVersion('req-1', 99)).rejects.toThrow(
      'That version no longer exists',
    );
  });
});
