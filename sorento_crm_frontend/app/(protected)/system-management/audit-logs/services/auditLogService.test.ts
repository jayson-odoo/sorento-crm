import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api';
import { getAuditLogs } from './auditLogService';

const mockedFetch = vi.mocked(apiFetch);

function okResponse(body: unknown): Response {
  return {
    ok: true,
    json: async () => body,
  } as Response;
}

function jsonErrorResponse(status: number, detail: string): Response {
  return {
    ok: false,
    status,
    headers: { get: () => 'application/json' },
    json: async () => ({ detail }),
    text: async () => JSON.stringify({ detail }),
  } as unknown as Response;
}

function calledUrl(): string {
  return mockedFetch.mock.calls[0][0] as string;
}

beforeEach(() => vi.clearAllMocks());

describe('getAuditLogs', () => {
  it('hits the /api/v1/audit/logs/ endpoint with 1-based page and limit', async () => {
    mockedFetch.mockResolvedValue(
      okResponse({ data: [], pagination: { total: 0, page: 1, limit: 50 }, empty: true }),
    );

    await getAuditLogs({ pageIndex: 0, pageSize: 50 });

    const url = calledUrl();
    expect(url).toContain('/api/v1/audit/logs/?');
    expect(url).toContain('page=1');
    expect(url).toContain('limit=50');
  });

  it('translates pageIndex to the 1-based page param', async () => {
    mockedFetch.mockResolvedValue(
      okResponse({ data: [], pagination: { total: 0, page: 3, limit: 25 }, empty: true }),
    );

    await getAuditLogs({ pageIndex: 2, pageSize: 25 });

    const url = calledUrl();
    expect(url).toContain('page=3');
    expect(url).toContain('limit=25');
  });

  it('includes entity_type, action and user_id filter params when supplied', async () => {
    mockedFetch.mockResolvedValue(
      okResponse({ data: [], pagination: { total: 0, page: 1, limit: 50 }, empty: true }),
    );

    await getAuditLogs({
      pageIndex: 0,
      pageSize: 50,
      entity_type: 'complaint',
      entity_id: 'abc-123',
      user_id: 'user-9',
      action: 'UPDATE',
    });

    const url = calledUrl();
    expect(url).toContain('entity_type=complaint');
    expect(url).toContain('entity_id=abc-123');
    expect(url).toContain('user_id=user-9');
    expect(url).toContain('action=UPDATE');
  });

  it('omits filter params that are empty/undefined', async () => {
    mockedFetch.mockResolvedValue(
      okResponse({ data: [], pagination: { total: 0, page: 1, limit: 50 }, empty: true }),
    );

    await getAuditLogs({ pageIndex: 0, pageSize: 50, entity_type: '', action: undefined });

    const url = calledUrl();
    expect(url).not.toContain('entity_type=');
    expect(url).not.toContain('action=');
    expect(url).not.toContain('user_id=');
  });

  it('returns the parsed envelope on success', async () => {
    const envelope = {
      data: [{ id: '1', entity_type: 'complaint', entity_id: 'e1', action: 'UPDATE', changed_at: '2026-06-30T00:00:00Z' }],
      pagination: { total: 1, page: 1, limit: 50 },
      empty: false,
    };
    mockedFetch.mockResolvedValue(okResponse(envelope));

    const out = await getAuditLogs({ pageIndex: 0, pageSize: 50 });
    expect(out.data).toHaveLength(1);
    expect(out.pagination.total).toBe(1);
  });

  it('throws an extracted API error message on a non-ok response', async () => {
    mockedFetch.mockResolvedValue(jsonErrorResponse(500, 'Boom in the audit service'));

    await expect(getAuditLogs({ pageIndex: 0, pageSize: 50 })).rejects.toThrow(
      'Boom in the audit service',
    );
  });
});
