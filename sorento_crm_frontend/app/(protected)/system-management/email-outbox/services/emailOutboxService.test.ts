/**
 * D-2 — email-outbox bulk retry/cancel service functions.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { bulkRetryEmailOutbox, bulkCancelEmailOutbox } from './emailOutboxService';
import { apiFetch } from '@/lib/api';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

const mockFetch = vi.mocked(apiFetch);

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as unknown as Response;
}
function fail(status: number, body: unknown) {
  return {
    ok: false,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

describe('email-outbox bulk service', () => {
  beforeEach(() => mockFetch.mockReset());

  it('bulk-retry POSTs row_ids to the bulk-retry endpoint', async () => {
    mockFetch.mockResolvedValueOnce(ok({ requested: 2, succeeded: 2, failed: 0, failed_ids: [] }));
    const res = await bulkRetryEmailOutbox(['a', 'b']);
    expect(res.succeeded).toBe(2);
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe('/api/v1/system/email-outbox/bulk-retry');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual({ row_ids: ['a', 'b'] });
  });

  it('bulk-cancel hits the bulk-cancel endpoint', async () => {
    mockFetch.mockResolvedValueOnce(ok({ requested: 1, succeeded: 0, failed: 1, failed_ids: ['x'] }));
    const res = await bulkCancelEmailOutbox(['x']);
    expect(res.failed_ids).toEqual(['x']);
    expect(mockFetch.mock.calls[0][0]).toBe('/api/v1/system/email-outbox/bulk-cancel');
  });

  it('throws an extracted error on non-ok', async () => {
    mockFetch.mockResolvedValueOnce(fail(403, { detail: 'nope' }));
    await expect(bulkRetryEmailOutbox(['a'])).rejects.toThrow();
  });
});
