import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api';
import { getAuditLogs } from './auditLogService';

const mockedFetch = vi.mocked(apiFetch);

function okResponse(body: unknown): Response {
  return { ok: true, json: async () => body } as Response;
}

/** The full request URL as a parsed URL for structured query assertions. */
function calledUrl(): URL {
  return new URL(mockedFetch.mock.calls[0][0] as string, 'http://localhost');
}

beforeEach(() => vi.clearAllMocks());

describe('getAuditLogs — changed_from / changed_to (System Health drill-down)', () => {
  it('adds changed_from and changed_to to the request params when supplied', async () => {
    mockedFetch.mockResolvedValue(
      okResponse({ data: [], pagination: { total: 0, page: 1, limit: 50 }, empty: true }),
    );

    await getAuditLogs({
      pageIndex: 0,
      pageSize: 50,
      changed_from: '2026-07-02T00:00:00.000Z',
      changed_to: '2026-07-02T23:59:59.999Z',
    });

    const url = calledUrl();
    expect(url.pathname).toBe('/api/v1/audit/logs/');
    expect(url.searchParams.get('changed_from')).toBe('2026-07-02T00:00:00.000Z');
    expect(url.searchParams.get('changed_to')).toBe('2026-07-02T23:59:59.999Z');
  });

  it('omits the date bounds when they are empty/undefined', async () => {
    mockedFetch.mockResolvedValue(
      okResponse({ data: [], pagination: { total: 0, page: 1, limit: 50 }, empty: true }),
    );

    await getAuditLogs({ pageIndex: 0, pageSize: 50, changed_from: '', changed_to: undefined });

    const url = calledUrl();
    expect(url.searchParams.has('changed_from')).toBe(false);
    expect(url.searchParams.has('changed_to')).toBe(false);
  });

  it('can send only a lower bound (changed_from without changed_to)', async () => {
    mockedFetch.mockResolvedValue(
      okResponse({ data: [], pagination: { total: 0, page: 1, limit: 50 }, empty: true }),
    );

    await getAuditLogs({
      pageIndex: 0,
      pageSize: 50,
      changed_from: '2026-07-01T00:00:00.000Z',
    });

    const url = calledUrl();
    expect(url.searchParams.get('changed_from')).toBe('2026-07-01T00:00:00.000Z');
    expect(url.searchParams.has('changed_to')).toBe(false);
  });
});
