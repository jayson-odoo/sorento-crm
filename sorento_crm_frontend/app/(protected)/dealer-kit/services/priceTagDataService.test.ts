/**
 * The CRM's door to the product-data gate and the version history
 * (r9 S5/D18-D19, AC-S5-4 / AC-S5-6 service half).
 *
 * Phase 1 answered every function from the in-memory store in
 * `lib/dealer-kit/product-data-changes.ts` so the screens could be walked
 * before the columns existed. Phase 2 swaps each body for the real call and no
 * caller changes, so what is asserted here is the wire: path, method, body.
 *
 * `updateAllTagPins` (AC-S5-4) is retired (AC-C4, PLAN-price-tag-currency-token-
 * extract-prompt.md section C): "Update all" is gone from the header, so a
 * salesperson clicks into the record to see what changed instead of firing one
 * loop over every changed tag. The grep gate at the end of this file is what
 * stops the function or the button that called it drifting back in.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import {
  listTagDataChanges,
  listRequestVersions,
  resolveTagPin,
  restoreRequestVersion,
} from './priceTagDataService';

const mockFetch = vi.mocked(apiFetch);

const BASE = '/api/v1/dealer-kit/price-tag-requests';

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as never;
}

function fail(status: number, message: string) {
  // `extractApiError` reads `content-type` FIRST and only parses JSON when it
  // says so; a stub without headers falls into the text branch and answers the
  // fallback instead of the server's message (repo convention, see
  // app/(protected)/sla-management/message-snippets/services/messageSnippetService.test.ts).
  return {
    ok: false,
    status,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => ({ message }),
    text: async () => JSON.stringify({ message }),
  } as never;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('listTagDataChanges (AC-S5-3)', () => {
  it('reads the resolver output the page already asks the server for', async () => {
    mockFetch.mockResolvedValue(
      ok([
        {
          tag_id: 'tag-1',
          tag_label: '1a',
          line_id: 'line-1',
          code: 'ZZT-SINK-1',
          name: 'ZZT Kitchen Sink',
          changes: [
            { field: 'list_price', label: 'List price', old: 'RM 1,000', new: 'RM 1,200' },
          ],
        },
      ]),
    );

    const sets = await listTagDataChanges('req-1');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(String(mockFetch.mock.calls[0][0])).toContain(`${BASE}/req-1`);
    expect(sets).toHaveLength(1);
    expect(sets[0].changes[0].field).toBe('list_price');
  });

  it('a terminal request carries no changes and that is not an error', async () => {
    mockFetch.mockResolvedValue(ok([]));

    await expect(listTagDataChanges('req-1')).resolves.toEqual([]);
  });
});

describe('resolveTagPin (AC-S5-5)', () => {
  it.each(['update', 'keep'] as const)('posts the %s decision for that line', async (action) => {
    mockFetch.mockResolvedValue(ok({ tag_id: 'tag-1', pinned_at: '2026-09-14T00:00:00Z' }));

    await resolveTagPin('req-1', 'tag-1', action);

    expect(mockFetch.mock.calls[0][0]).toBe(`${BASE}/req-1/tags/tag-1/pin`);
    const init = mockFetch.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({ action });
  });

  it('raises the server message so the dialog can stay open', async () => {
    mockFetch.mockResolvedValue(fail(409, 'This request is finished'));

    await expect(resolveTagPin('req-1', 'tag-1', 'update')).rejects.toThrow(
      'This request is finished',
    );
  });
});

// ---------------------------------------------------------------------------
// AC-C4 (PLAN-price-tag-currency-token-extract-prompt.md section C): "Update
// all" is gone - a salesperson clicks into the record to see what changed
// instead. `updateAllTagPins` above (AC-S5-4) is retired along with it; this
// grep gate is what stops it, or the button that called it, drifting back in.
// ---------------------------------------------------------------------------

describe('priceTagDataService - updateAllTagPins retired (AC-C4)', () => {
  it('the module no longer exports updateAllTagPins', async () => {
    const mod: Record<string, unknown> = await import('./priceTagDataService');
    expect('updateAllTagPins' in mod).toBe(false);
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
