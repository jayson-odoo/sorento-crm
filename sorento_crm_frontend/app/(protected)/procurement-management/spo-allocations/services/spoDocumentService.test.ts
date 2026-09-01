/**
 * spoDocumentService - the FE->BE contract for the SPO document list + form view
 * (PLAN-spo-investigation-grid.md S1/S2; UAC AC-11, AC-16, AC-16b).
 *
 * Pins:
 *   - `listSPODocuments` builds the query string via `buildDataGridParams`
 *     (page/limit/sort/dir/query) plus the document filters (`state` default
 *     outstanding, `product_id`, `warehouse_id`, `overdue_only`) - AC-11.
 *   - `getSPODocument` GETs the slash-encoded path param, 404 -> null - AC-16.
 *   - every call surfaces the backend error via `extractApiError` on failure.
 *
 * Bulk delete (AC-16b) has no service function of its own any more (review B4) -
 * `useDeferredBulkAction` parks the `spo_document.delete` pending action directly
 * through `services/pendingActionService`, which has its own tests.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { listSPODocuments, getSPODocument } from './spoDocumentService';

function ok(body: unknown) {
  return {
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => body,
  } as unknown as Response;
}
function fail(detail: string, status = 400) {
  return {
    ok: false,
    status,
    headers: { get: () => 'application/json' },
    json: async () => ({ detail }),
    text: async () => JSON.stringify({ detail }),
  } as unknown as Response;
}
function notFound() {
  return {
    ok: false,
    status: 404,
    headers: { get: () => 'application/json' },
    json: async () => ({ detail: 'Not found' }),
    text: async () => JSON.stringify({ detail: 'Not found' }),
  } as unknown as Response;
}
function calledUrl(): URL {
  const calls = apiFetch.mock.calls;
  return new URL(String(calls[calls.length - 1][0]), 'http://x');
}
beforeEach(() => apiFetch.mockReset());

describe('spoDocumentService - listSPODocuments (AC-11)', () => {
  it('GETs /spo-allocations/documents with buildDataGridParams page/limit/sort/dir/query', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { page: 1, total: 0 } }));
    await listSPODocuments({
      pageIndex: 1,
      pageSize: 25,
      sortField: 'earliest_eta',
      sortDir: 'desc',
      searchQuery: 'SPO-2026',
    });
    const u = calledUrl();
    expect(u.pathname).toBe('/api/v1/procurement/spo-allocations/documents');
    expect(u.searchParams.get('page')).toBe('2'); // 0-based index 1 -> 1-based page 2
    expect(u.searchParams.get('limit')).toBe('25');
    expect(u.searchParams.get('sort')).toBe('earliest_eta');
    expect(u.searchParams.get('dir')).toBe('desc');
    expect(u.searchParams.get('query')).toBe('SPO-2026');
  });

  it('defaults state to outstanding when unset', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { page: 1, total: 0 } }));
    await listSPODocuments({ pageIndex: 0, pageSize: 25 });
    expect(calledUrl().searchParams.get('state')).toBe('outstanding');
  });

  it('composes state, product_id, warehouse_id and overdue_only on the query string', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { page: 1, total: 0 } }));
    await listSPODocuments({
      pageIndex: 0,
      pageSize: 25,
      state: 'completed',
      product_id: 'prod-1',
      warehouse_id: 'wh-1',
      overdue_only: true,
    });
    const u = calledUrl();
    expect(u.searchParams.get('state')).toBe('completed');
    expect(u.searchParams.get('product_id')).toBe('prod-1');
    expect(u.searchParams.get('warehouse_id')).toBe('wh-1');
    expect(u.searchParams.get('overdue_only')).toBe('true');
  });

  it('omits overdue_only, product_id and warehouse_id when unset', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { page: 1, total: 0 } }));
    await listSPODocuments({ pageIndex: 0, pageSize: 25 });
    const u = calledUrl();
    expect(u.searchParams.get('overdue_only')).toBeNull();
    expect(u.searchParams.get('product_id')).toBeNull();
    expect(u.searchParams.get('warehouse_id')).toBeNull();
  });

  it('surfaces the backend error on a failed list', async () => {
    apiFetch.mockResolvedValue(fail('Module disabled', 403));
    await expect(listSPODocuments({ pageIndex: 0, pageSize: 25 })).rejects.toThrow(
      'Module disabled',
    );
  });
});

describe('spoDocumentService - getSPODocument (AC-16)', () => {
  it('GETs the slash-encoded spo_number path param', async () => {
    apiFetch.mockResolvedValue(
      ok({ spo_number: 'SPO-2026/08-0061', lines: [] }),
    );
    await getSPODocument('SPO-2026/08-0061');
    expect(calledUrl().pathname).toBe(
      '/api/v1/procurement/spo-allocations/documents/SPO-2026%2F08-0061',
    );
  });

  it('returns null on 404 (unknown SPO number)', async () => {
    apiFetch.mockResolvedValue(notFound());
    const result = await getSPODocument('SPO-UNKNOWN');
    expect(result).toBeNull();
  });

  it('surfaces the backend error on a non-404 failure', async () => {
    apiFetch.mockResolvedValue(fail('Module disabled', 403));
    await expect(getSPODocument('SPO-2026/08-0061')).rejects.toThrow('Module disabled');
  });
});
